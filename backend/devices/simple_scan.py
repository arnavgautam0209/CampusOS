"""
POST /api/scan/: the AttendX hardware contract for classroom attendance.

Request (JSON):  {"card_uid": "A1B2C3D4", "classroom": "ECE"}
Same rules and data as /api/v1/devices/scan/, with the field names and
response shape the ESP32 firmware expects. See firmware/README.md.

Authentication: `Authorization: Device <key>` as usual. For local testing only,
CAMPUSOS_OPEN_SCAN=1 (with DJANGO_DEBUG on) also accepts requests without a key
and attributes them to the classroom's registered reader.
"""

import logging
import re

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance import services as attendance
from attendance.models import UID_PATTERN, Classroom

from .authentication import DeviceKeyAuthentication
from .models import Device, ScanEvent
from .scanning import log_scan, scan_for_attendance

log = logging.getLogger(__name__)
Result = ScanEvent.Result


def open_scan_enabled():
    return settings.DEBUG and settings.CAMPUSOS_OPEN_SCAN


class SimpleScanView(APIView):
    # Device keys only: no session authentication, so no cookies or CSRF token are needed.
    authentication_classes = [DeviceKeyAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        if not request.content_type.startswith("application/json"):
            return self.invalid({"body": "Send JSON with the header Content-Type: application/json."})
        data = request.data if isinstance(request.data, dict) else {}

        errors = {}
        raw_uid = str(data.get("card_uid") or "")
        uid = attendance.normalize_uid(raw_uid)
        if not raw_uid.strip():
            errors["card_uid"] = "card_uid is required, e.g. A1B2C3D4."
        elif not re.match(UID_PATTERN, uid):
            errors["card_uid"] = "card_uid must be 4, 7 or 10 bytes of hex, e.g. A1B2C3D4."
        requested_room = str(data.get("classroom") or "").strip()
        classroom = Classroom.objects.filter(pk__iexact=requested_room).first() if requested_room else None
        if not requested_room:
            errors["classroom"] = "classroom is required, e.g. ECE."
        elif classroom is None:
            errors["classroom"] = f"Unknown classroom {requested_room}. Add it in admin → Classrooms."
        if errors:
            return self.invalid(errors)

        device = request.auth if isinstance(request.auth, Device) else None
        if device is None:
            if not open_scan_enabled():
                return self.reply(status.HTTP_401_UNAUTHORIZED, "unauthorized",
                                  "Send the header Authorization: Device <key>. For local testing only, "
                                  "start the server with CAMPUSOS_OPEN_SCAN=1.")
            device = Device.objects.filter(classroom=classroom, is_active=True).order_by("id").first()
            if device is None:
                return self.invalid({"classroom": f"No reader is registered for {classroom.id}. "
                                                  "Add one in admin → Devices."})
        elif device.classroom_id != classroom.id:
            log_scan(device, uid, requested_room, Result.WRONG_CLASSROOM)
            return self.invalid({"classroom": f"This reader is registered to "
                                              f"{device.classroom_id or device.lab_id or 'nothing'}, "
                                              f"not {requested_room}."})

        Device.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
        scan = scan_for_attendance(device, uid, classroom.id)

        if scan.result == Result.UNKNOWN_CARD:
            return self.reply(status.HTTP_404_NOT_FOUND, "unknown_card", "Card is not registered",
                              card_uid=uid, classroom=classroom.id)
        if scan.result == Result.NO_SESSION:
            return self.reply(status.HTTP_409_CONFLICT, "no_session",
                              f"No attendance session is open in {classroom.id}",
                              card_uid=uid, classroom=classroom.id)

        created = scan.result == Result.MARKED
        student = scan.card.user
        return self.reply(
            status.HTTP_201_CREATED if created else status.HTTP_200_OK, "present",
            "Attendance marked successfully" if created else "Attendance already marked",
            created=created,
            student=attendance.display_name(student),
            roll_number=attendance.roll_number_for(student, classroom.id),
            classroom=classroom.id,
            card_uid=uid,
            session=scan.session.title,
            marked_at=scan.record.marked_at.isoformat(),
        )

    def handle_exception(self, exc):
        # Keep every answer JSON in the same shape, including auth errors and crashes.
        if isinstance(exc, (APIException, Http404)):
            response = super().handle_exception(exc)
            detail = response.data.get("detail", "") if isinstance(response.data, dict) else ""
            code = "unauthorized" if response.status_code in (401, 403) else "error"
            response.data = {"status": code, "message": str(detail) or "Request failed"}
            return response
        log.exception("Scan failed")
        return self.reply(status.HTTP_500_INTERNAL_SERVER_ERROR, "error", "Server error. Try again.")

    @staticmethod
    def reply(http_status, result, message, **extra):
        return Response({"status": result, "message": message, **extra}, status=http_status)

    def invalid(self, errors):
        return self.reply(status.HTTP_400_BAD_REQUEST, "error", next(iter(errors.values())), errors=errors)
