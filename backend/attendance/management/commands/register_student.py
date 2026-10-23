import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from attendance.models import UID_PATTERN, CampusCard
from attendance.services import normalize_uid


class Command(BaseCommand):
    help = ("Register a student (username = roll number) and link their RFID card UID. "
            "The student can't sign in to the app until a password is set with changepassword.")

    def add_arguments(self, parser):
        parser.add_argument("roll_number", help="e.g. ECE001 (used as the username)")
        parser.add_argument("card_uid", help="card UID from the reader, e.g. A1B2C3D4 or a1:b2:c3:d4")
        parser.add_argument("--name", default="", help='full name, e.g. "Asha Verma"')

    @transaction.atomic
    def handle(self, *args, **options):
        uid = normalize_uid(options["card_uid"])
        if not re.match(UID_PATTERN, uid):
            raise CommandError("card_uid must be 4, 7 or 10 bytes of hex, e.g. A1B2C3D4.")
        roll = options["roll_number"].strip()
        if not roll:
            raise CommandError("roll_number is required.")

        User = get_user_model()
        student, created = User.objects.get_or_create(username=roll)
        if created:
            student.set_unusable_password()
        if options["name"]:
            first, _, last = options["name"].strip().partition(" ")
            student.first_name, student.last_name = first, last
        student.save()

        card = CampusCard.objects.filter(uid=uid).select_related("user").first()
        if card and card.user_id != student.pk:
            raise CommandError(f"Card {uid} already belongs to {card.user.get_username()}. "
                               "Deactivate or reassign it in admin → Campus cards first.")
        if card:
            card.is_active = True
            card.save(update_fields=["is_active"])
        else:
            CampusCard.objects.create(uid=uid, user=student)

        name = student.get_full_name() or roll
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} student {roll} ({name}) with card {uid}."))
