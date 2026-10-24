from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import rules
from .models import SafetyAlert, SensorReading


def parse_reading(data):
    """Validates {"temperature_c", "humidity_pct", "gas_raw"}; each optional (a sensor read can fail)."""
    values, errors = {}, {}
    for field, (low, high) in rules.RANGES.items():
        raw = data.get(field)
        if raw is None:
            continue
        is_number = isinstance(raw, (int, float)) and not isinstance(raw, bool)
        if not is_number or not (low <= raw <= high):
            errors[field] = f"{field} must be a number from {low} to {high} (omit it or send null if the read failed)."
            continue
        values[field] = int(raw) if field == "gas_raw" else float(raw)
    if not errors and not values:
        errors["body"] = "Send at least one of temperature_c, humidity_pct or gas_raw."
    if errors:
        raise ValidationError(errors)
    return values


def record(device, values, source=SensorReading.Source.DEVICE, now=None):
    """Stores a reading for the device's lab and opens, raises or clears alerts. Returns (reading, findings)."""
    now = now or timezone.now()
    findings = rules.assess(**values)
    level = rules.worst(level for _, level, _, _ in findings)
    with transaction.atomic():
        reading = SensorReading.objects.create(device=device, lab_id=device.lab_id, level=level,
                                               source=source, **values)
        _update_alerts(device.lab_id, findings, values, now)
    return reading, findings


def _update_alerts(lab_id, findings, values, now):
    abnormal = {kind for kind, _, _, _ in findings}
    for kind, level, value, message in findings:
        alert = SafetyAlert.objects.select_for_update().filter(
            lab_id=lab_id, kind=kind, acknowledged_at__isnull=True).first()
        if alert is None:
            try:
                with transaction.atomic():
                    SafetyAlert.objects.create(lab_id=lab_id, kind=kind, level=level, message=message,
                                               value=value, last_seen_at=now)
            except IntegrityError:
                pass  # another reading opened it at the same moment
            continue
        alert.last_seen_at = now
        alert.cleared_at = None
        alert.value = value
        if rules.SEVERITY[level] > rules.SEVERITY[alert.level]:
            alert.level, alert.message = level, message  # escalate; never downgrade an open alert
        alert.save()

    # Kinds that were measured this time and are back to normal: note when they cleared.
    measured = {kind for field, kind in [("temperature_c", SafetyAlert.Kind.TEMPERATURE),
                                         ("humidity_pct", SafetyAlert.Kind.HUMIDITY),
                                         ("gas_raw", SafetyAlert.Kind.GAS)] if field in values}
    SafetyAlert.objects.filter(lab_id=lab_id, kind__in=measured - abnormal, acknowledged_at__isnull=True,
                               cleared_at__isnull=True).update(cleared_at=now)


def acknowledge(alert, user):
    if not user.is_staff:
        raise PermissionDenied("Only faculty can acknowledge safety alerts.")
    if alert.acknowledged_at:
        raise ValidationError({"alert": "This alert was already acknowledged."})
    alert.acknowledged_at = timezone.now()
    alert.acknowledged_by = user
    alert.save(update_fields=["acknowledged_at", "acknowledged_by"])
    return alert

