import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

# (username, first, last, admin, password environment variable)
ACCOUNTS = [
    ("demo_student", "Demo", "Student", False, "DEMO_STUDENT_PASSWORD"),
    ("demo_admin", "Demo", "Admin", True, "DEMO_ADMIN_PASSWORD"),
]


class Command(BaseCommand):
    help = ("Create the request/approval demo accounts demo_student and demo_admin, plus demo labs and equipment. "
            "Passwords come from DEMO_STUDENT_PASSWORD / DEMO_ADMIN_PASSWORD; without them a password is generated "
            "and printed once, only when the account is first created. Safe to rerun: existing passwords are only "
            "changed when the variable is set.")

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        for username, first, last, admin, variable in ACCOUNTS:
            user, created = User.objects.get_or_create(username=username,
                                                       defaults={"first_name": first, "last_name": last})
            user.is_staff = user.is_superuser = admin
            password = os.environ.get(variable)
            if password:
                user.set_password(password)
                note = f"password from {variable}"
            elif created:
                password = secrets.token_urlsafe(12)
                user.set_password(password)
                note = f"generated password (shown once, local only): {password}"
            else:
                note = f"password unchanged (set {variable} to change it)"
            user.save()
            role = "admin" if admin else "student"
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {role} {username}: {note}"))
