"""
Attendance rules for card scans. Deterministic checks only; a marked record
means "this card was tapped while the session was open", not verified identity.
"""

from django.db import IntegrityError, transaction

from .models import AttendanceRecord, AttendanceSession, CampusCard


def normalize_uid(raw):
    """'04:a1:b2:c3' / '04 A1 B2 C3' / '04a1b2c3' → '04A1B2C3'."""
    return "".join(ch for ch in str(raw) if ch not in " :-").upper()


def display_name(user):
    return user.get_full_name() or user.get_username()


def open_session_for(classroom_id):
    return AttendanceSession.objects.filter(classroom_id=classroom_id, closed_at__isnull=True).first()


def active_card(uid):
    return CampusCard.objects.filter(uid=uid, is_active=True).select_related("user").first()


def mark_from_card(session, card, device=None):
    """Returns (record, created). Safe against two readers racing on the same student."""
    try:
        with transaction.atomic():
            record, created = AttendanceRecord.objects.get_or_create(
                session=session, student=card.user,
                defaults={"card": card, "device": device, "source": AttendanceRecord.Source.CARD},
            )
    except IntegrityError:
        record, created = AttendanceRecord.objects.get(session=session, student=card.user), False
    return record, created
