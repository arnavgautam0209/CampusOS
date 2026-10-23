from django.core.management.base import BaseCommand, CommandError

from devices.models import Device


class Command(BaseCommand):
    help = "Issue a new secret key for a reader (replaces its old key) and print it once."

    def add_arguments(self, parser):
        parser.add_argument("device_id", help="e.g. READER-ROOM-101")

    def handle(self, *args, **options):
        device = Device.objects.filter(pk=options["device_id"]).first()
        if device is None:
            raise CommandError(f"No device {options['device_id']}. Run seed_demo or add it in /admin/.")
        key = device.issue_key()
        self.stdout.write(f"New key for {device.id} (copy it into the ESP32's secrets.h; it won't be shown again):")
        self.stdout.write(key)
