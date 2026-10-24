from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from devices.models import Device
from safelab import services
from safelab.models import SensorReading


class Command(BaseCommand):
    help = ("Record a SIMULATED sensor reading for demos without hardware. "
            "It is stored and shown in the app as simulated, never as a real measurement.")

    def add_arguments(self, parser):
        parser.add_argument("sensor", help="sensor device ID, e.g. SENSOR-LAB002")
        parser.add_argument("--temp", type=float, help="temperature °C")
        parser.add_argument("--humidity", type=float, help="relative humidity %%")
        parser.add_argument("--gas", type=int, help="MQ-2 raw value 0-4095")

    def handle(self, *args, **options):
        device = Device.objects.filter(pk=options["sensor"]).first()
        if device is None or not device.lab_id:
            raise CommandError(f"No sensor {options['sensor']} registered to a lab. Run seed_demo or add it in admin.")
        data = {"temperature_c": options["temp"], "humidity_pct": options["humidity"], "gas_raw": options["gas"]}
        try:
            values = services.parse_reading(data)
        except ValidationError as error:
            raise CommandError(str(next(iter(error.detail.values()))))
        reading, findings = services.record(device, values, source=SensorReading.Source.SIMULATED)
        self.stdout.write(self.style.SUCCESS(f"Simulated {device.lab.name}: {reading.level}"))
        for _, _, _, message in findings:
            self.stdout.write(f"  {message}")
