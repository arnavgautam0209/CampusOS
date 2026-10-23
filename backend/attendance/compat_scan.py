"""AttendX local-demo compatibility endpoint. Never enable without DEBUG and explicit opt-in."""
import re

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from attendance.models import UID_PATTERN, Classroom
from attendance.services import active_card, display_name, mark_from_card, normalize_uid, open_session_for


def reply(code, result, message, **kwargs):
    return Response({"status": result, "message": message, **kwargs}, status=code)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def local_scan(request):
    """POST /api/scan/: {"card_uid": "A1B2C3D4", "classroom": "ECE"}."""
    if not (settings.DEBUG and getattr(settings, "ATTENDX_ALLOW_UNAUTHENTICATED_SCAN", False)):
        return reply(status.HTTP_403_FORBIDDEN, "disabled", "Unauthenticated scan endpoint is disabled.")

    if not isinstance(request.data, dict):
        return reply(400, "invalid_request", "Expected a JSON object.")
    raw_uid = request.data.get("card_uid")
    raw_room = request.data.get("classroom")
    if not isinstance(raw_uid, str) or not isinstance(raw_room, str):
        return reply(400, "invalid_request", "card_uid and classroom must be strings.")
    uid = normalize_uid(raw_uid)
    classroom_id = raw_room.strip()
    if not re.fullmatch(UID_PATTERN, uid):
        return reply(400, "invalid_request", "card_uid must contain 4, 7 or 10 bytes of hexadecimal digits.")
    if not classroom_id or len(classroom_id) > 32:
        return reply(400, "invalid_request", "classroom must be a nonempty classroom ID (max 32 characters).")
    if not Classroom.objects.filter(pk=classroom_id).exists():
        return reply(400, "invalid_request", "Unknown classroom ID.")

    card = active_card(uid)
    if card is None:
        return reply(404, "unknown_card", "Card is not registered", created=False)
    session = open_session_for(classroom_id)
    if session is None:
        return reply(409, "no_session", "No open attendance session for this classroom.", created=False)

    record, created = mark_from_card(session, card)
    user = card.user
    return reply(
        201 if created else 200,
        "present",
        "Attendance marked successfully" if created else "Attendance already marked",
        created=created,
        student=display_name(user),
        roll_number=user.get_username(),  # Existing auth user has no dedicated roll-number field.
        classroom=classroom_id,
        session_id=session.id,
        marked_at=record.marked_at.isoformat(),
    )
