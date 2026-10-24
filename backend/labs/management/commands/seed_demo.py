import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework.authtoken.models import Token

from labs.models import Equipment, Lab
from attendance.models import Classroom
from devices.models import Device
from skillpass.models import Certification

# Started from DemoLabs.all in ios/CampusOS/Core/Models/Lab.swift (the app now loads labs from the API).
DEMO_LABS = [
    {
        "id": "LAB001", "name": "Robotics Lab", "location": "Block A · 204",
        "symbol": "cpu", "capacity": 30, "is_open_for_booking": True,
        "equipment": [
            ("EQ001", "ESP32 Kits", "Embedded", True),
            ("EQ002", "Robotic Arm", "Robotics", True),
            ("EQ003", "Soldering Station", "Tools", True),
            ("EQ008", "Arduino Uno Boards", "Embedded", True),
            ("EQ009", "DC Gear Motors", "Components", True),
        ],
    },
    {
        "id": "LAB002", "name": "Electronics Lab", "location": "Block B · 102",
        "symbol": "bolt", "capacity": 40, "is_open_for_booking": True,
        "equipment": [
            ("EQ004", "Oscilloscope", "Testing", True),
            ("EQ005", "Multimeter", "Testing", True),
        ],
    },
    {
        "id": "LAB003", "name": "3D Printing Lab", "location": "Innovation Centre",
        "symbol": "printer", "capacity": 15, "is_open_for_booking": False,
        "equipment": [
            ("EQ006", "3D Printer", "Fabrication", False),
        ],
    },
    {
        "id": "LAB004", "name": "AI & Computing Lab", "location": "Block C · 301",
        "symbol": "desktopcomputer", "capacity": 50, "is_open_for_booking": True,
        "equipment": [
            ("EQ007", "GPU Workstation", "Computing", True),
        ],
    },
]

# SkillPass catalogue. Seeding never grants certifications: faculty must approve them.
DEMO_CERTIFICATIONS = [
    ("CERT-ELEC-BASIC", "Basic Electronics Safety",
     "Safe use of bench power supplies, oscilloscopes and multimeters.", 365),
    ("CERT-SOLDER", "Soldering Station Training", "Hot tools, fume extraction and burn first aid.", 180),
    ("CERT-ROBOT-ARM", "Robotic Arm Operation", "Motion envelopes, emergency stop and supervised use.", 180),
    ("CERT-3DP", "3D Printer Operation", "Printer setup, materials and fire safety.", 365),
]
LAB_REQUIREMENTS = {"LAB002": ["CERT-ELEC-BASIC"]}
# AssetX stock: (total units, low-stock threshold, loanable). Not listed: 1 unit, lab use only.
STOCK = {
    "EQ001": (20, 4, True),    # ESP32 Kits
    "EQ003": (6, 1, False),    # Soldering Station
    "EQ004": (8, 2, True),     # Oscilloscope (needs Basic Electronics Safety)
    "EQ005": (15, 3, True),    # Multimeter
    "EQ007": (4, 1, False),    # GPU Workstation
    "EQ008": (25, 5, True),    # Arduino Uno Boards
    "EQ009": (40, 8, True),    # DC Gear Motors
}
EQUIPMENT_REQUIREMENTS = {
    "EQ002": ["CERT-ROBOT-ARM"],
    "EQ003": ["CERT-SOLDER"],
    "EQ004": ["CERT-ELEC-BASIC"],
    "EQ006": ["CERT-3DP"],
}

# Attendance demo: one classroom with one reader. Keys come from `manage.py device_key`.
DEMO_CLASSROOMS = [("ROOM-101", "Lecture Room 101, Block A"), ("ECE", "ECE Classroom")]
DEMO_DEVICES = [("READER-ROOM-101", "Room 101 card reader", "ROOM-101"),
                ("READER-ECE", "ECE classroom reader (AttendX ESP32-S3)", "ECE")]
# Lab door readers check students in to their booking.
DEMO_LAB_READERS = [("READER-LAB001", "Robotics Lab door reader", "LAB001")]

DEMO_USERNAME = "demo_student"


class Command(BaseCommand):
    help = "Load demo labs, equipment, SkillPass certifications, a classroom and a reader (safe to rerun)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demo-user", action="store_true",
            help=f"Also create '{DEMO_USERNAME}'. Password comes from CAMPUSOS_DEMO_PASSWORD "
                 "or is generated and printed once.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        for lab_data in DEMO_LABS:
            lab_data = dict(lab_data)
            equipment = lab_data.pop("equipment")
            lab, _ = Lab.objects.update_or_create(id=lab_data.pop("id"), defaults=lab_data)
            for eq_id, name, category, available in equipment:
                Equipment.objects.update_or_create(
                    id=eq_id,
                    defaults={"lab": lab, "name": name, "category": category, "is_available": available},
                )
        for cert_id, name, description, validity_days in DEMO_CERTIFICATIONS:
            Certification.objects.update_or_create(
                id=cert_id, defaults={"name": name, "description": description, "validity_days": validity_days})
        for lab_id, cert_ids in LAB_REQUIREMENTS.items():
            Lab.objects.get(pk=lab_id).required_certifications.set(cert_ids)
        for equipment_id, (total, low, loanable) in STOCK.items():
            Equipment.objects.filter(pk=equipment_id).update(
                total_quantity=total, low_stock_threshold=low, is_loanable=loanable)
        for equipment_id, cert_ids in EQUIPMENT_REQUIREMENTS.items():
            Equipment.objects.get(pk=equipment_id).required_certifications.set(cert_ids)
        for classroom_id, name in DEMO_CLASSROOMS:
            Classroom.objects.update_or_create(id=classroom_id, defaults={"name": name})
        for device_id, name, classroom_id in DEMO_DEVICES:
            Device.objects.update_or_create(id=device_id, defaults={"name": name, "classroom_id": classroom_id})
        for device_id, name, lab_id in DEMO_LAB_READERS:
            Device.objects.update_or_create(id=device_id, defaults={"name": name, "lab_id": lab_id})
        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS(
                f"Seeded {len(DEMO_LABS)} demo labs, {len(DEMO_CERTIFICATIONS)} certifications, "
                f"{len(DEMO_CLASSROOMS)} classrooms, {len(DEMO_DEVICES)} classroom readers and "
                f"{len(DEMO_LAB_READERS)} lab reader."))
            for device_id, *_ in DEMO_DEVICES + DEMO_LAB_READERS:
                if not Device.objects.filter(id=device_id).exclude(key_hash="").exists():
                    self.stdout.write(f"Issue {device_id}'s key with: manage.py device_key {device_id}")

        if options["demo_user"]:
            self._create_demo_user()

    def _create_demo_user(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(username=DEMO_USERNAME)
        if created:
            password = os.environ.get("CAMPUSOS_DEMO_PASSWORD") or secrets.token_urlsafe(12)
            user.set_password(password)
            user.save()
            if "CAMPUSOS_DEMO_PASSWORD" not in os.environ:
                self.stdout.write(f"Generated password for {DEMO_USERNAME}: {password}")
        token, _ = Token.objects.get_or_create(user=user)
        self.stdout.write(self.style.SUCCESS(f"Demo user '{DEMO_USERNAME}' ready. API token: {token.key}"))
