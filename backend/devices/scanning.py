"""
Classroom attendance from a card tap, shared by both scan endpoints:
/api/v1/devices/scan/ (CampusOS contract) and /api/scan/ (AttendX contract).
"""

from typing import NamedTuple, Optional

from attendance import services as attendance

from .models import ScanEvent

Result = ScanEvent.Result


class AttendanceScan(NamedTuple):
    result: str                       # marked, duplicate, unknown_card or no_session
    card: Optional[object] = None
    session: Optional[object] = None
    record: Optional[object] = None


def log_scan(device, uid, location_id, result, student=None, session=None, booking=None, reason=""):
    ScanEvent.objects.create(device=device, uid=uid[:20], classroom_id_sent=location_id[:32],
                             result=result, student=student, session=session, booking=booking,
                             reason=reason)


def scan_for_attendance(device, uid, classroom_id):
    """`uid` is already normalized and `device` is registered to `classroom_id`."""
    card = attendance.active_card(uid)
    if card is None:
        log_scan(device, uid, classroom_id, Result.UNKNOWN_CARD)
        return AttendanceScan(Result.UNKNOWN_CARD)

    session = attendance.open_session_for(classroom_id)
    if session is None:
        log_scan(device, uid, classroom_id, Result.NO_SESSION, student=card.user)
        return AttendanceScan(Result.NO_SESSION, card=card)

    record, created = attendance.mark_from_card(session, card, device)
    result = Result.MARKED if created else Result.DUPLICATE
    log_scan(device, uid, classroom_id, result, student=card.user, session=session)
    return AttendanceScan(result, card=card, session=session, record=record)
