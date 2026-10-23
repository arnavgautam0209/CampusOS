import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework.authtoken.models import Token

from labs.models import Equipment, Lab

# Mirrors DemoLabs.all in ios/CampusOS/Core/Models/Lab.swift.
DEMO_LABS = [
    {
        "id": "LAB001", "name": "Robotics Lab", "location": "Block A · 204",
        "symbol": "cpu", "capacity": 30, "is_open_for_booking": True,
        "equipment": [
            ("EQ001", "ESP32 Kits", "Embedded", True),
            ("EQ002", "Robotic Arm", "Robotics", True),
            ("EQ003", "Soldering Station", "Tools", True),
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

DEMO_USERNAME = "demo_student"


class Command(BaseCommand):
    help = "Load the demo labs and equipment (safe to run repeatedly)."

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
        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS(f"Seeded {len(DEMO_LABS)} demo labs."))

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
