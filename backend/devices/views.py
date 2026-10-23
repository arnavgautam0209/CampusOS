import re

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import UnsupportedMediaType
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance import services as attendance
from attendance.models import UID_PATTERN
from bookings import services as bookings

from .authentication import DeviceKeyAuthentication, IsDevice
from .models import ScanEvent
from .scanning import log_scan, scan_for_attendance

Result = ScanEvent.Result


class ScanView(APIView):
    """
    POST /api/v1/devices/scan/   (Authorization: Device <key>)

    Contract for the ESP32 firmware (see firmware/README.md). Every response has a
    short "message" for the serial monitor / OLED.

    Classroom readers send {"uid": "04A1B2C3", "classroomId": "ROOM-101"}:
      201 marked · 200 duplicate · 404 unknown_card · 409 no_session
    Lab door readers send {"uid": "04A1B2C3", "labId": "LAB001"}:
      201 granted · 200 already_checked_in · 403 denied (+ reason) · 404 unknown_card
    Both: 400 bad input · 401 bad key
    """

    authentication_classes = [DeviceKeyAuthentication]
    permission_classes = [IsDevice]

    def post(self, request):
        device = request.auth
        Device = type(device)
        Device.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())

        # Without this header DRF would parse the body as a form and report a confusing uid error.
        if not request.content_type.startswith("application/json"):
            return self.error("Send JSON with the header Content-Type: application/json.")
        data = request.data if isinstance(request.data, dict) else {}
        uid = attendance.normalize_uid(data.get("uid", ""))
        classroom_id = str(data.get("classroomId", "")).strip()
        if not re.match(UID_PATTERN, uid):
            return self.error("uid must be 4, 7 or 10 bytes of hex, e.g. 04A1B2C3.")
        if device.lab_id:
            return self.lab_check_in(device, uid, str(data.get("labId", "")).strip())
        if not device.classroom_id:
            return self.error("This reader isn't assigned to a classroom or lab yet.")
        if not classroom_id:
            return self.error("classroomId is required, e.g. ROOM-101.")
        if device.classroom_id != classroom_id:
            self.log(device, uid, classroom_id, Result.WRONG_CLASSROOM)
            return self.error(f"This reader is registered to {device.classroom_id}, not {classroom_id}.")

        scan = scan_for_attendance(device, uid, classroom_id)
        if scan.result == Result.UNKNOWN_CARD:
            return self.reply(status.HTTP_404_NOT_FOUND, Result.UNKNOWN_CARD,
                              f"Card {uid} is not registered.", uid=uid)
        if scan.result == Result.NO_SESSION:
            return self.reply(status.HTTP_409_CONFLICT, Result.NO_SESSION,
                              f"No attendance session is open in {classroom_id}.", uid=uid)

        created = scan.result == Result.MARKED
        name = attendance.display_name(scan.card.user)
        message = f"Attendance marked: {name}" if created else f"Already marked: {name}"
        return self.reply(status.HTTP_201_CREATED if created else status.HTTP_200_OK, scan.result, message,
                          uid=uid, student=name, sessionId=scan.session.id, session=scan.session.title,
                          markedAt=scan.record.marked_at.isoformat())

    def lab_check_in(self, device, uid, lab_id):
        if not lab_id:
            return self.error("labId is required for lab readers, e.g. LAB001.")
        if lab_id != device.lab_id:
            self.log(device, uid, lab_id, Result.WRONG_CLASSROOM)
            return self.error(f"This reader is registered to {device.lab_id}, not {lab_id}.")

        card = attendance.active_card(uid)
        if card is None:
            self.log(device, uid, lab_id, Result.UNKNOWN_CARD)
            return self.reply(status.HTTP_404_NOT_FOUND, Result.UNKNOWN_CARD,
                              f"Card {uid} is not registered.", uid=uid)

        outcome = bookings.check_in(card.user, device.lab, device)
        self.log(device, uid, lab_id, outcome.result, student=card.user, booking=outcome.booking,
                 reason=outcome.reason)
        name = attendance.display_name(card.user)
        extra = {"uid": uid, "student": name, "labId": lab_id}
        if outcome.booking:
            extra.update(bookingId=str(outcome.booking.id), start=outcome.booking.start.isoformat(),
                         end=outcome.booking.end.isoformat(),
                         checkedInAt=outcome.booking.checked_in_at.isoformat()
                         if outcome.booking.checked_in_at else None)
        if outcome.result == Result.DENIED:
            extra["reason"] = outcome.reason
            if outcome.missing:
                extra["missingCertifications"] = [cert.id for cert in outcome.missing]
            http_status = status.HTTP_403_FORBIDDEN
        else:
            http_status = status.HTTP_201_CREATED if outcome.result == Result.GRANTED else status.HTTP_200_OK
        return self.reply(http_status, outcome.result, f"{name}: {outcome.message}", **extra)

    def handle_exception(self, exc):
        # The firmware contract only knows 400 for bad input, so wrong content types become 400 too.
        if isinstance(exc, UnsupportedMediaType):
            return self.error("Send JSON with the header Content-Type: application/json.")
        # Give 401s and other framework errors the same "message" field the firmware prints.
        response = super().handle_exception(exc)
        if isinstance(response.data, dict) and "detail" in response.data:
            response.data["message"] = str(response.data["detail"])
        return response

    @staticmethod
    def reply(http_status, result, message, **extra):
        return Response({"result": result, "message": message, **extra}, status=http_status)

    @staticmethod
    def error(message):
        return Response({"message": message, "detail": message}, status=status.HTTP_400_BAD_REQUEST)

    log = staticmethod(log_scan)
