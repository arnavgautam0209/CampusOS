"""
Demo data for the screenshot walkthrough (scripts/walkthrough.sh).

Everything it creates is separate from real data: users start with "demo_ui_",
attendance happens in its own DEMO-ROOM with its own reader, the lab check-in
uses its own demo door reader, and card UIDs use reserved demo values. Real rooms, readers, keys and cards are never touched.
`--clean` removes exactly what this command creates.
"""

import os
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

from attendance.models import AttendanceSession, CampusCard, Classroom
from bookings.services import create_booking
from devices.models import Device
from skillpass.models import UserCertification

PREFIX = "demo_ui_"
ROOM_ID, ROOM_NAME = "DEMO-ROOM", "Demo Lecture Room"
READER_ID = "READER-DEMO"
LAB_READER_ID = "READER-DEMO-LAB"
CHECK_IN_LAB = "LAB001"
SESSION_TITLE = "CS201 Embedded Systems · Lecture 5"
# (username, first, last, staff, card UID)
PEOPLE = [
    ("student", "Aarav", "Mehta", False, "D1D1D1D1"),
    ("faculty", "Meera", "Iyer", True, None),
    ("kabir", "Kabir", "Rao", False, "D2D2D2D2"),
    ("sara", "Sara", "Khan", False, "D3D3D3D3"),
]
# Taps sent by the demo reader: two classmates, an unknown card, the student, a repeat.
TAPS = ["D2D2D2D2", "D3D3D3D3", "DEADBEEF", "D1D1D1D1", "D2D2D2D2"]


class Command(BaseCommand):
    help = "Create (or with --clean, remove) demo data for the screenshot walkthrough."

    def add_arguments(self, parser):
        parser.add_argument("--clean", action="store_true", help="Remove the walkthrough demo data.")

    def handle(self, *args, **options):
        if options["clean"]:
            self.clean()
            return
        password = os.environ.get("CAMPUSOS_WALKTHROUGH_PASSWORD")
        if not password:
            raise CommandError("Set CAMPUSOS_WALKTHROUGH_PASSWORD (scripts/walkthrough.sh generates one).")
        call_command("seed_demo", verbosity=0)
        self.clean(quiet=True)
        self.seed(password)

    @transaction.atomic
    def seed(self, password):
        User = get_user_model()
        users = {}
        for key, first, last, staff, uid in PEOPLE:
            user = User.objects.create_user(f"{PREFIX}{key}", email=f"{PREFIX}{key}@example.edu",
                                            password=password, first_name=first, last_name=last,
                                            is_staff=staff)
            users[key] = user
            if uid:
                if CampusCard.objects.filter(uid=uid).exists():
                    raise CommandError(f"Card {uid} is already registered to a real user; not touching it.")
                CampusCard.objects.create(uid=uid, user=user)

        student, faculty = users["student"], users["faculty"]
        now = timezone.now()
        UserCertification.objects.create(user=student, certification_id="CERT-SOLDER", status="approved",
                                         approved_by=faculty, approved_at=now,
                                         expires_at=now + timedelta(days=180))
        UserCertification.objects.create(user=student, certification_id="CERT-ELEC-BASIC", status="pending")

        # A booking in two days, through the normal rules so it never overlaps anyone else's.
        day = timezone.localdate() + timedelta(days=2)
        for hour in range(14, 18):
            start = timezone.make_aware(datetime.combine(day, time(hour, 0)))
            try:
                create_booking(student, "LAB004", start, 60)
                break
            except APIException:
                continue

        Classroom.objects.create(id=ROOM_ID, name=ROOM_NAME)
        reader = Device.objects.create(id=READER_ID, name="Demo card reader", classroom_id=ROOM_ID)
        AttendanceSession.objects.create(classroom_id=ROOM_ID, title=SESSION_TITLE, opened_by=faculty)
        client = APIClient(HTTP_HOST="localhost")
        client.credentials(HTTP_AUTHORIZATION=f"Device {reader.issue_key()}")
        for uid in TAPS:
            response = client.post("/api/v1/devices/scan/", {"uid": uid, "classroomId": ROOM_ID}, format="json")
            if response.status_code >= 500:
                raise CommandError(f"Demo tap {uid} failed: {response.status_code}")

        # Lab check-in: a booking starting in a few minutes, tapped at a demo door reader.
        door = Device.objects.create(id=LAB_READER_ID, name="Demo lab door reader", lab_id=CHECK_IN_LAB)
        start = (timezone.now() + timedelta(minutes=5)).replace(second=0, microsecond=0)
        try:
            create_booking(student, CHECK_IN_LAB, start, 60)
        except APIException:
            self.stdout.write("Robotics Lab is booked right now, so the demo skips the check-in.")
        else:
            client.credentials(HTTP_AUTHORIZATION=f"Device {door.issue_key()}")
            client.post("/api/v1/devices/scan/", {"uid": "D1D1D1D1", "labId": CHECK_IN_LAB}, format="json")
        self.stdout.write(self.style.SUCCESS(
            f"Walkthrough demo data ready: {len(PEOPLE)} demo users, {ROOM_NAME}, {len(TAPS)} reader taps."))

    @transaction.atomic
    def clean(self, quiet=False):
        AttendanceSession.objects.filter(classroom_id=ROOM_ID).delete()
        Device.objects.filter(pk__in=[READER_ID, LAB_READER_ID]).delete()  # also deletes their scan logs
        Classroom.objects.filter(pk=ROOM_ID).delete()
        deleted, _ = get_user_model().objects.filter(username__startswith=PREFIX).delete()
        if not quiet:
            self.stdout.write(f"Removed walkthrough demo data ({deleted} objects with the demo users).")
