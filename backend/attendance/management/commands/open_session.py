from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException

from attendance import services
from attendance.services import open_session_for


class Command(BaseCommand):
    help = "Open (or with --close, close) the attendance session for a classroom, e.g. for hardware testing."

    def add_arguments(self, parser):
        parser.add_argument("classroom", help="classroom ID, e.g. ECE")
        parser.add_argument("title", nargs="?", default="Hardware test session")
        parser.add_argument("--close", action="store_true", help="close the open session instead")

    def handle(self, *args, **options):
        classroom = options["classroom"]
        try:
            if options["close"]:
                session = open_session_for(classroom)
                if session is None:
                    raise CommandError(f"No open session in {classroom}.")
                services.close_session(session, None)
                self.stdout.write(self.style.SUCCESS(
                    f"Closed {session.title} in {classroom} ({session.records.count()} present)."))
            else:
                session = services.open_session(classroom, options["title"], None)
                self.stdout.write(self.style.SUCCESS(f"Opened {session.title} in {classroom}. Readers can mark now."))
        except APIException as error:
            detail = error.detail
            if isinstance(detail, dict):  # e.g. {"title": ["..."]}
                detail = next(iter(detail.values()))
            if isinstance(detail, list):
                detail = detail[0]
            raise CommandError(str(detail))
