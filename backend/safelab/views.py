from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from devices.authentication import DeviceKeyAuthentication, IsDevice
from devices.models import Device
from labs.models import Lab

from . import rules, services
from .models import SafetyAlert, SensorReading

OFFLINE_AFTER = timedelta(minutes=2)
HISTORY_POINTS = 40


class TelemetryView(APIView):
    """
    POST /api/v1/telemetry/   (Authorization: Device <key>, sensor registered to a lab)
    Body: {"temperature_c": 24.5, "humidity_pct": 48.0, "gas_raw": 812}  (any field may be omitted)
    201 {"status": "recorded", "level": "normal"|"warning"|"danger", "message", "alerts": [...]}
    The level is advisory: the sensor node must run its own local alarm.
    """

    authentication_classes = [DeviceKeyAuthentication]
    permission_classes = [IsDevice]

    def post(self, request):
        device = request.auth
        Device.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
        if not request.content_type.startswith("application/json"):
            return self.error("Send JSON with the header Content-Type: application/json.")
        if not device.lab_id:
            return self.error("This sensor isn't assigned to a lab. Set its Lab in admin → Devices.")
        data = request.data if isinstance(request.data, dict) else {}
        values = services.parse_reading(data)
        reading, findings = services.record(device, values)
        messages = [message for _, _, _, message in findings]
        summary = "; ".join(messages) if messages else "All readings normal"
        return Response({"status": "recorded", "level": reading.level, "message": f"{device.lab.name}: {summary}",
                         "alerts": messages}, status=status.HTTP_201_CREATED)

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if isinstance(response.data, dict):
            detail = response.data.get("detail") or next(iter(response.data.values()), "")
            response.data = {"status": "error", "message": str(detail), "errors": response.data}
        return response

    @staticmethod
    def error(message):
        return Response({"status": "error", "message": message}, status=status.HTTP_400_BAD_REQUEST)


def _reading_json(reading):
    return {
        "temperatureC": reading.temperature_c,
        "humidityPct": reading.humidity_pct,
        "gasRaw": reading.gas_raw,
        "level": reading.level,
        "simulated": reading.source == SensorReading.Source.SIMULATED,
        "recordedAt": reading.recorded_at.isoformat(),
    }


def _alert_json(alert):
    return {
        "id": alert.id,
        "kind": alert.kind,
        "level": alert.level,
        "message": alert.message,
        "value": alert.value,
        "openedAt": alert.opened_at.isoformat(),
        "lastSeenAt": alert.last_seen_at.isoformat(),
        "clearedAt": alert.cleared_at.isoformat() if alert.cleared_at else None,
    }


@api_view(["GET"])
def dashboard(request):
    """
    GET /api/v1/safelab/ : live conditions for every lab with a sensor (signed-in users).
    Status: the latest reading's level, "offline" if no reading for 2 minutes, raised to an
    open alert's level so nothing un-acknowledged is hidden.
    """
    now = timezone.now()
    sensors = {}
    for device in Device.objects.filter(lab__isnull=False, readings__isnull=False).distinct():
        sensors.setdefault(device.lab_id, []).append(device)
    open_alerts = {}
    for alert in SafetyAlert.objects.filter(acknowledged_at__isnull=True):
        open_alerts.setdefault(alert.lab_id, []).append(alert)

    labs = []
    for lab in Lab.objects.filter(pk__in=set(sensors) | set(open_alerts)).order_by("id"):
        history = list(SensorReading.objects.filter(lab=lab)[:HISTORY_POINTS])
        latest = history[0] if history else None
        online = latest is not None and now - latest.recorded_at <= OFFLINE_AFTER
        alerts = open_alerts.get(lab.id, [])
        level = latest.level if online else "offline"
        alert_level = rules.worst(alert.level for alert in alerts)
        if alerts and (level == "offline" or rules.SEVERITY[alert_level] > rules.SEVERITY[level]):
            level = alert_level
        labs.append({
            "labId": lab.id,
            "labName": lab.name,
            "status": level,
            "online": online,
            "sensors": [{"id": d.id, "name": d.name,
                         "lastSeenAt": d.last_seen_at.isoformat() if d.last_seen_at else None}
                        for d in sensors.get(lab.id, [])],
            "latest": _reading_json(latest) if latest else None,
            "history": [_reading_json(r) for r in reversed(history)],
            "alerts": [_alert_json(a) for a in alerts],
        })
    return Response({
        "generatedAt": now.isoformat(),
        "labs": labs,
        "thresholds": {"temperatureC": rules.TEMPERATURE_C, "humidityPct": rules.HUMIDITY_PCT,
                       "gasRaw": rules.GAS_RAW},
    })


@api_view(["POST"])
def acknowledge(request, pk):
    """POST /api/v1/safelab/alerts/{id}/acknowledge/ : faculty only."""
    alert = services.acknowledge(get_object_or_404(SafetyAlert, pk=pk), request.user)
    return Response(_alert_json(alert) | {"acknowledgedBy": request.user.get_username()})
