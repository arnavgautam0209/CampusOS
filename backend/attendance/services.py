"""
Attendance rules for card scans. Deterministic checks only; a marked record
means "this card was tapped while the session was open", not verified identity.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from .models import AttendanceRecord, AttendanceSession, CampusCard, Classroom, ClassroomEnrollment


def normalize_uid(raw):
    """'04:a1:b2:c3' / '04 A1 B2 C3' / '04a1b2c3' → '04A1B2C3'."""
    return "".join(ch for ch in str(raw) if ch not in " :-").upper()


def display_name(user):
    return user.get_full_name() or user.get_username()


def roll_number_for(student, classroom_id):
    """The student's roll number on that classroom's roster, or their username if they aren't enrolled."""
    enrollment = ClassroomEnrollment.objects.filter(
        classroom_id=classroom_id, student=student, left_at__isnull=True).only("roll_number").first()
    return enrollment.roll_number if enrollment else student.get_username()


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


class SessionAlreadyOpen(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "session_already_open"


def open_session(classroom_id, title, opened_by):
    title = (title or "").strip()
    if not title:
        raise ValidationError({"title": "Give the session a title, e.g. CS201 Lecture 5."})
    if len(title) > 120:
        raise ValidationError({"title": "Keep the title under 120 characters."})
    classroom = Classroom.objects.filter(pk=classroom_id).first()
    if classroom is None:
        raise ValidationError({"classroomId": f"Unknown classroom {classroom_id}."})
    existing = open_session_for(classroom.id)
    if existing is not None:
        raise SessionAlreadyOpen(f"{classroom.name} already has an open session: {existing.title}.")
    try:
        with transaction.atomic():
            return AttendanceSession.objects.create(classroom=classroom, title=title, opened_by=opened_by)
    except IntegrityError:
        # Another faculty member opened one at the same moment (DB constraint).
        raise SessionAlreadyOpen(f"{classroom.name} already has an open session.")


def close_session(session, closed_by):
    if session.closed_at is not None:
        raise ValidationError({"session": "This session is already closed."})
    session.closed_at = timezone.now()
    session.closed_by = closed_by
    session.save(update_fields=["closed_at", "closed_by"])
    return session
