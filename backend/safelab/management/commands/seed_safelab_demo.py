from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from labs.models import Equipment, Lab
from safelab.models import EquipmentFault

# Fictional demo labs added for SafeLab (the other labs come from seed_demo).
LABS = [
    ("LAB005", "Mac Lab", "Block C · 105", "desktopcomputer", 30),
    ("LAB006", "IoT Lab", "Innovation Centre · 2", "antenna.radiowaves.left.and.right", 24),
]
# (asset ID, lab, name, equipment type). Existing items (EQ002 Robotic Arm, EQ004 Oscilloscope,
# EQ006 3D Printer) are reused as they are.
EQUIPMENT = [
    ("MAC-IMAC-01", "LAB005", "iMac 01", "Computer"),
    ("MAC-IMAC-02", "LAB005", "iMac 02", "Computer"),
    ("MAC-IMAC-03", "LAB005", "iMac 03", "Computer"),
    ("MAC-KBD-01", "LAB005", "Magic Keyboard", "Peripheral"),
    ("MAC-MOUSE-01", "LAB005", "Magic Mouse", "Peripheral"),
    ("MAC-MON-01", "LAB005", "External Monitor", "Display"),
    ("MAC-HUB-01", "LAB005", "USB-C Hub", "Peripheral"),
    ("MAC-PROJ-01", "LAB005", "Projector", "Display"),
    ("IOT-ARD-01", "LAB006", "Arduino Uno", "Microcontroller"),
    ("IOT-ESP32-01", "LAB006", "ESP32 Development Board", "Microcontroller"),
    ("IOT-RPI-01", "LAB006", "Raspberry Pi", "Microcontroller"),
    ("IOT-BRD-01", "LAB006", "Breadboard", "Prototyping"),
    ("IOT-DHT11-01", "LAB006", "DHT11 Sensor", "Sensor"),
    ("IOT-ULTRA-01", "LAB006", "Ultrasonic Sensor", "Sensor"),
    ("IOT-SERVO-01", "LAB006", "Servo Motor", "Actuator"),
    ("IOT-MM-01", "LAB006", "Multimeter", "Test Instrument"),
    ("ROB-MDRV-01", "LAB001", "Motor Driver", "Actuator"),
    ("ROB-DCM-01", "LAB001", "DC Motor", "Actuator"),
    ("ROB-SERVO-01", "LAB001", "Servo Motor", "Actuator"),
    ("ELE-FGEN-01", "LAB002", "Function Generator", "Test Instrument"),
    ("ELE-PSU-01", "LAB002", "DC Power Supply", "Test Instrument"),
    ("ELE-SOLD-01", "LAB002", "Soldering Station", "Tools"),
    ("3DP-DRY-01", "LAB003", "Filament Dryer", "Fabrication"),
]
# Fictional reporters for the history, so real accounts aren't involved.
REPORTERS = [("safelab_demo_1", "Aarav", "Shah"), ("safelab_demo_2", "Diya", "Kapoor"),
             ("safelab_demo_3", "Rohan", "Iyer")]
C, S, St = EquipmentFault.Category, EquipmentFault.Severity, EquipmentFault.Status
# (days ago, asset ID, category, severity, status, description)
HISTORY = [
    (170, "MAC-IMAC-01", C.NOT_WORKING, S.HIGH, St.RESOLVED, "Won't power on after the weekend."),
    (160, "IOT-ESP32-01", C.UNEXPECTED_BEHAVIOUR, S.MEDIUM, St.RESOLVED, "Resets randomly while uploading code."),
    (152, "ELE-PSU-01", C.PARTIALLY_WORKING, S.HIGH, St.RESOLVED, "Current limit knob does nothing."),
    (140, "MAC-MOUSE-01", C.PHYSICALLY_DAMAGED, S.LOW, St.RESOLVED, "Bottom cover cracked, scroll is stuck."),
    (131, "IOT-SERVO-01", C.NOT_WORKING, S.MEDIUM, St.REJECTED, "Doesn't move."),
    (122, "EQ004", C.UNEXPECTED_BEHAVIOUR, S.HIGH, St.RESOLVED, "Channel 2 trace drifts off screen."),
    (118, "IOT-DHT11-01", C.NOT_WORKING, S.LOW, St.RESOLVED, "Always reads zero over the data pin."),
    (110, "MAC-IMAC-02", C.PARTIALLY_WORKING, S.MEDIUM, St.RESOLVED, "Display flickers at full brightness."),
    (101, "ROB-MDRV-01", C.PHYSICALLY_DAMAGED, S.HIGH, St.RESOLVED, "Burn mark near the H-bridge chip."),
    (94, "IOT-ESP32-01", C.NOT_WORKING, S.HIGH, St.RESOLVED, "USB port loose, board not detected."),
    (88, "MAC-PROJ-01", C.PARTIALLY_WORKING, S.MEDIUM, St.RESOLVED, "Image has a purple tint."),
    (80, "ELE-SOLD-01", C.NOT_WORKING, S.CRITICAL, St.RESOLVED, "Tip doesn't heat up at all."),
    (73, "MAC-IMAC-01", C.UNEXPECTED_BEHAVIOUR, S.MEDIUM, St.RESOLVED, "Kernel panic when opening Xcode."),
    (66, "IOT-ULTRA-01", C.PARTIALLY_WORKING, S.LOW, St.REJECTED, "Distance readings are a bit off."),
    (60, "EQ006", C.NOT_WORKING, S.HIGH, St.RESOLVED, "Nozzle clogged, nothing extrudes."),
    (52, "MAC-KBD-01", C.PHYSICALLY_DAMAGED, S.LOW, St.RESOLVED, "Spacebar key cap broken."),
    (45, "IOT-ESP32-01", C.PHYSICALLY_DAMAGED, S.MEDIUM, St.UNDER_MAINTENANCE, "Antenna trace scratched off."),
    (40, "ROB-DCM-01", C.NOT_WORKING, S.MEDIUM, St.RESOLVED, "Motor hums but shaft doesn't turn."),
    (33, "EQ002", C.UNEXPECTED_BEHAVIOUR, S.CRITICAL, St.APPROVED, "Arm jerks at joint 3 during homing."),
    (27, "MAC-IMAC-03", C.NOT_WORKING, S.HIGH, St.APPROVED, "Stuck on the Apple logo."),
    (21, "ELE-FGEN-01", C.PARTIALLY_WORKING, S.MEDIUM, St.APPROVED, "Square wave output is distorted."),
    (16, "IOT-RPI-01", C.NOT_WORKING, S.MEDIUM, St.REJECTED, "SD card was missing, not a fault."),
    (12, "MAC-HUB-01", C.PARTIALLY_WORKING, S.LOW, St.PENDING, "HDMI port works, USB-A ports don't."),
    (8, "3DP-DRY-01", C.NOT_WORKING, S.MEDIUM, St.PENDING, "Doesn't heat above 30 °C."),
    (5, "MAC-IMAC-01", C.PHYSICALLY_DAMAGED, S.HIGH, St.PENDING, "Screen has a crack in the corner."),
    (2, "IOT-ARD-01", C.UNEXPECTED_BEHAVIOUR, S.LOW, St.PENDING, "Pin 13 LED stays on after reset."),
]


class Command(BaseCommand):
    help = ("SafeLab demo: adds Mac Lab and IoT Lab with fictional equipment (each with an asset ID) and fictional "
            "historical equipment fault reports for the charts. Safe to rerun: existing labs, equipment and reports "
            "are left as they are, and the history is created once.")

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_demo", verbosity=0)
        for lab_id, name, location, symbol, capacity in LABS:
            Lab.objects.get_or_create(id=lab_id, defaults={"name": name, "location": location, "symbol": symbol,
                                                           "capacity": capacity})
        added = 0
        for asset_id, lab_id, name, kind in EQUIPMENT:
            _, created = Equipment.objects.get_or_create(id=asset_id, defaults={"lab_id": lab_id, "name": name,
                                                                                "category": kind})
            added += created
        self.stdout.write(f"Equipment: {added} added, {len(EQUIPMENT) - added} already there.")

        User = get_user_model()
        reporters = []
        for username, first, last in REPORTERS:
            user, created = User.objects.get_or_create(username=username, defaults={"first_name": first,
                                                                                    "last_name": last})
            if created:
                user.set_unusable_password()
                user.save()
            reporters.append(user)
        if EquipmentFault.objects.filter(reporter__in=reporters).exists():
            self.stdout.write("Fault history already there; left unchanged.")
            return
        reviewer = User.objects.filter(is_staff=True).order_by("id").first()
        now = timezone.now()
        for index, (days, asset_id, category, severity, status, description) in enumerate(HISTORY):
            equipment = Equipment.objects.get(pk=asset_id)
            decided = status != St.PENDING
            EquipmentFault.objects.create(
                equipment=equipment, lab_id=equipment.lab_id, reporter=reporters[index % len(reporters)],
                category=category, severity=severity, description=description, status=status,
                decided_by=reviewer if decided else None, created_at=now - timedelta(days=days),
                decision_note="Not an equipment fault." if status == St.REJECTED else "")
        # Keep AssetX consistent with reports still under maintenance.
        Equipment.objects.filter(faults__status=St.UNDER_MAINTENANCE).update(is_available=False)
        self.stdout.write(self.style.SUCCESS(f"Added {len(HISTORY)} fictional historical fault reports."))
