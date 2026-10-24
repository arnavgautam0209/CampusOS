from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Level(models.TextChoices):
    NORMAL = "normal", "Normal"
    WARNING = "warning", "Warning"
    DANGER = "danger", "Danger"


class SensorReading(models.Model):
    """One telemetry message from a lab sensor node (ESP32 + DHT22 + MQ-2)."""

    class Source(models.TextChoices):
        DEVICE = "device", "Sensor node"
        SIMULATED = "simulated", "Simulated (demo)"

    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE, related_name="readings")
    lab = models.ForeignKey("labs.Lab", on_delete=models.CASCADE, related_name="readings")
    temperature_c = models.FloatField(null=True, blank=True)
    humidity_pct = models.FloatField(null=True, blank=True)
    gas_raw = models.PositiveIntegerField(null=True, blank=True,
                                          help_text="MQ-2 analog reading, 0-4095 on the ESP32 ADC. Not calibrated ppm.")
    level = models.CharField(max_length=16, choices=Level.choices)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.DEVICE)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [models.Index(fields=["lab", "-recorded_at"])]

    def __str__(self):
        return f"{self.lab_id} {self.recorded_at:%H:%M:%S} {self.level}"


class SafetyAlert(models.Model):
    """Opened when readings leave the normal range; stays until faculty acknowledge it."""

    class Kind(models.TextChoices):
        TEMPERATURE = "temperature", "Temperature"
        HUMIDITY = "humidity", "Humidity"
        GAS = "gas", "Gas / smoke"

    lab = models.ForeignKey("labs.Lab", on_delete=models.CASCADE, related_name="safety_alerts")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    level = models.CharField(max_length=16, choices=Level.choices)
    message = models.CharField(max_length=200)
    value = models.FloatField(help_text="The latest out-of-range value.")
    opened_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    cleared_at = models.DateTimeField(null=True, blank=True, help_text="When readings returned to normal.")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="+")

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["lab", "kind"], condition=Q(acknowledged_at__isnull=True),
                                    name="one_open_alert_per_lab_and_kind"),
        ]

    def __str__(self):
        return f"{self.lab_id} {self.kind} {self.level}"


class EquipmentFault(models.Model):
    """A student's report that one specific piece of lab equipment is faulty. Equipment faults only."""

    class Category(models.TextChoices):
        NOT_WORKING = "not_working", "Not Working"
        PARTIALLY_WORKING = "partially_working", "Partially Working"
        PHYSICALLY_DAMAGED = "physically_damaged", "Physically Damaged"
        UNEXPECTED_BEHAVIOUR = "unexpected_behaviour", "Unexpected Behaviour"
        OTHER = "other", "Other Equipment Fault"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        UNDER_MAINTENANCE = "under_maintenance", "Under Maintenance"
        RESOLVED = "resolved", "Resolved"

    equipment = models.ForeignKey("labs.Equipment", on_delete=models.PROTECT, related_name="faults")
    lab = models.ForeignKey("labs.Lab", on_delete=models.PROTECT, related_name="equipment_faults")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="equipment_faults")
    category = models.CharField(max_length=32, choices=Category.choices)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    description = models.CharField(max_length=500)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    decision_note = models.CharField(max_length=300, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.equipment_id} {self.category} ({self.status})"
