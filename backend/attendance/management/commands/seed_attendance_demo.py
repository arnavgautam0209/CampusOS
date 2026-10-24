from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceRecord, AttendanceSession, CampusCard, Classroom, ClassroomEnrollment
from devices.models import Device

CLASSROOM_ID = "ECE"
SESSION_TITLE = "Embedded Systems Lecture 01"
FACULTY_USERNAME = "demo_faculty"
# (roll number = username, name, sample card UID, taps in the demo session)
STUDENTS = [
    ("ECE001", "Aarav Sharma", "A1B2C3D4", True),
    ("ECE002", "Riya Verma", "B1C2D3E4", True),
    ("ECE003", "Kabir Mehta", "C1D2E3F4", False),
    ("ECE004", "Ananya Singh", "D1E2F3A4", False),
]


class Command(BaseCommand):
    help = ("Create the four-student ECE roster and a closed 'Embedded Systems Lecture 01' session in which only "
            "ECE001 and ECE002 tapped, for the attendance report demo. Safe to rerun; never changes existing "
            "users or cards that don't match the demo data. Students get no password (they don't sign in).")

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        classroom, _ = Classroom.objects.get_or_create(id=CLASSROOM_ID, defaults={"name": "ECE Classroom"})
        faculty = User.objects.filter(username=FACULTY_USERNAME).first()
        if faculty is None:
            faculty = User(username=FACULTY_USERNAME, first_name="Demo", last_name="Faculty", is_staff=True)
            faculty.set_unusable_password()
            faculty.save()
            self.stdout.write(f"Created {FACULTY_USERNAME} without a password: "
                              f"set one with manage.py changepassword {FACULTY_USERNAME}")
        elif not faculty.is_staff:
            raise CommandError(f"{FACULTY_USERNAME} exists but isn't staff; not changing it.")

        session = AttendanceSession.objects.filter(classroom=classroom, title=SESSION_TITLE).first()
        # The demo lecture happened two hours ago; new demo enrollments date from the day before it.
        start = session.opened_at if session else timezone.now() - timedelta(hours=2)

        cards = {}
        for roll, name, uid, _ in STUDENTS:
            student = self.student(User, roll, name)
            cards[roll] = self.card(student, uid)
            self.enroll(classroom, student, roll, enrolled_at=start - timedelta(days=1))

        if session is None:
            session = self.create_session(classroom, faculty, start, cards)
            self.stdout.write(self.style.SUCCESS(
                f"Created session {session.id} '{SESSION_TITLE}' in {CLASSROOM_ID}: 2 of 4 present."))
        else:
            self.stdout.write(f"Session {session.id} '{SESSION_TITLE}' already exists; left unchanged.")
        self.stdout.write(f"Report: GET /api/v1/attendance/sessions/{session.id}/report/ (and /report/pdf/)")

    def student(self, User, roll, name):
        first, _, last = name.partition(" ")
        student = User.objects.filter(username=roll).first()
        if student is None:
            student = User(username=roll, first_name=first, last_name=last)
            student.set_unusable_password()
            student.save()
        elif (student.first_name, student.last_name) != (first, last):
            raise CommandError(f"User {roll} already exists as '{student.get_full_name()}', not {name}; "
                               "not overwriting a real account.")
        return student

    def card(self, student, uid):
        card = CampusCard.objects.filter(uid=uid).first()
        if card is None:
            return CampusCard.objects.create(uid=uid, user=student)
        if card.user_id != student.pk:
            raise CommandError(f"Card {uid} belongs to another user; not reassigning it.")
        return card

    def enroll(self, classroom, student, roll, enrolled_at):
        current = ClassroomEnrollment.objects.filter(classroom=classroom, left_at__isnull=True)
        mine = current.filter(student=student).first()
        if mine is None:
            if current.filter(roll_number=roll).exists():
                raise CommandError(f"Roll number {roll} in {classroom.id} belongs to someone else.")
            ClassroomEnrollment.objects.create(classroom=classroom, student=student, roll_number=roll,
                                               enrolled_at=enrolled_at)
        elif mine.roll_number != roll:
            raise CommandError(f"{student.get_username()} is enrolled in {classroom.id} as {mine.roll_number}.")

    def create_session(self, classroom, faculty, start, cards):
        late = ClassroomEnrollment.objects.filter(classroom=classroom, left_at__isnull=True,
                                                  student__username__in=[s[0] for s in STUDENTS],
                                                  enrolled_at__gt=start)
        if late.exists():
            raise CommandError("A demo student was enrolled after the demo lecture would start, so they "
                               "wouldn't be on its roster. Remove their enrollment and rerun.")
        reader = Device.objects.filter(classroom=classroom, is_active=True).order_by("id").first()
        # Created closed, so it never counts as ECE's open session (a hardware test may be open).
        session = AttendanceSession.objects.create(classroom=classroom, title=SESSION_TITLE, opened_by=faculty,
                                                   closed_at=start + timedelta(minutes=50), closed_by=faculty)
        for minutes, (roll, _, _, taps) in zip((3, 5, 0, 0), STUDENTS):
            if taps:
                record = AttendanceRecord.objects.create(session=session, student=cards[roll].user,
                                                         card=cards[roll], device=reader)
                AttendanceRecord.objects.filter(pk=record.pk).update(marked_at=start + timedelta(minutes=minutes))
        # opened_at is auto_now_add, so the backdated times are written with update().
        AttendanceSession.objects.filter(pk=session.pk).update(opened_at=start)
        session.refresh_from_db()
        return session
