import re

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import UnsupportedMediaType
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance import services as attendance
from attendance.models import UID_PATTERN

from .authentication import DeviceKeyAuthentication, IsDevice
from .models import ScanEvent

Result = ScanEvent.Result


class ScanView(APIView):
    """
    POST /api/v1/devices/scan/   (Authorization: Device <key>)
    Body: {"uid": "04A1B2C3", "classroomId": "ROOM-101"}

    Contract for the ESP32 firmware (see firmware/README.md):
      201 marked · 200 duplicate · 404 unknown_card · 409 no_session · 400 bad input · 401 bad key
    Every response has a short "message" for the serial monitor / OLED.
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
        if not classroom_id:
            return self.error("classroomId is required, e.g. ROOM-101.")
        if device.classroom_id != classroom_id:
            self.log(device, uid, classroom_id, Result.WRONG_CLASSROOM)
            assigned = device.classroom_id or "no classroom"
            return self.error(f"This reader is registered to {assigned}, not {classroom_id}.")

        card = attendance.active_card(uid)
        if card is None:
            self.log(device, uid, classroom_id, Result.UNKNOWN_CARD)
            return self.reply(status.HTTP_404_NOT_FOUND, Result.UNKNOWN_CARD,
                              f"Card {uid} is not registered.", uid=uid)

        session = attendance.open_session_for(classroom_id)
        if session is None:
            self.log(device, uid, classroom_id, Result.NO_SESSION, student=card.user)
            return self.reply(status.HTTP_409_CONFLICT, Result.NO_SESSION,
                              f"No attendance session is open in {classroom_id}.", uid=uid)

        record, created = attendance.mark_from_card(session, card, device)
        result = Result.MARKED if created else Result.DUPLICATE
        self.log(device, uid, classroom_id, result, student=card.user, session=session)
        name = attendance.display_name(card.user)
        message = f"Attendance marked: {name}" if created else f"Already marked: {name}"
        return self.reply(status.HTTP_201_CREATED if created else status.HTTP_200_OK, result, message,
                          uid=uid, student=name, sessionId=session.id, session=session.title,
                          markedAt=record.marked_at.isoformat())

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

    @staticmethod
    def log(device, uid, classroom_id, result, student=None, session=None):
        ScanEvent.objects.create(device=device, uid=uid[:20], classroom_id_sent=classroom_id[:32],
                                 result=result, student=student, session=session)
