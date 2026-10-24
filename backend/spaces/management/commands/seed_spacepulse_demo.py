from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from attendance.models import Classroom
from spaces import capacity, timetables
from spaces.models import Timetable, TimetableEvent

DEMO_DIR = Path(settings.BASE_DIR) / "demo_data" / "spacepulse"
TIMETABLE_A = "Timetable_A_Initial.csv"
TIMETABLE_A_NAME = "Timetable A — Regular Semester Schedule"
# Fictional classrooms for Demo University Mode: (id, name, seats, location)
ROOMS = [
    ("ECE-101", "Electronics Classroom 101", 30, "ECE Block · Floor 1"),
    ("ECE-102", "Electronics Classroom 102", 45, "ECE Block · Floor 1"),
    ("IT-201", "Information Technology Room 201", 60, "IT Block · Floor 2"),
    ("CSE-301", "Computer Science Room 301", 75, "CSE Block · Floor 3"),
    ("SEM-01", "Seminar Room 01", 100, "Admin Block · Ground floor"),
    ("HALL-01", "Conference Hall 01", 150, "Admin Block · Ground floor"),
]


class Command(BaseCommand):
    help = ("Demo University Mode for SpacePulse: six fictional classrooms and Timetable A "
            f"(demo_data/spacepulse/{TIMETABLE_A}). Safe to rerun: existing rooms are left as they are, Timetable A "
            "is loaded once, and it's activated only if no timetable is active (an uploaded one is never replaced).")

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for room_id, name, seats, location in ROOMS:
            _, made = Classroom.objects.get_or_create(id=room_id, defaults={
                "name": name, "kind": Classroom.Kind.CLASSROOM, "capacity": seats, "location": location,
                "features": "Projector, Whiteboard", "is_bookable": True})
            created += made
        self.stdout.write(f"Classrooms: {created} created, {len(ROOMS) - created} already there.")

        timetable = Timetable.objects.filter(source_filename=TIMETABLE_A).order_by("version").first()
        if timetable is None:
            path = DEMO_DIR / TIMETABLE_A
            if not path.exists():
                raise CommandError(f"Missing {path}.")
            timetable = timetables.upload(None, TIMETABLE_A_NAME, path.read_text(encoding="utf-8"), TIMETABLE_A,
                                          action=TimetableEvent.Action.SEEDED)
            self.stdout.write(f"Loaded {TIMETABLE_A} as v{timetable.version} ({timetable.entries.count()} classes).")
        else:
            self.stdout.write(f"{TIMETABLE_A} already loaded as v{timetable.version}.")

        active = capacity.active_timetable()
        if active is None:
            timetables.activate(timetable, None, system=True)
            self.stdout.write(self.style.SUCCESS(f"Activated v{timetable.version} {timetable.name}."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Left the active timetable as it is: v{active.version} {active.name}."))
