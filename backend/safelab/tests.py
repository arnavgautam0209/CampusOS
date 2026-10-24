from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from devices.models import Device

from .models import SafetyAlert, SensorReading

TELEMETRY = "/api/v1/telemetry/"
DASHBOARD = "/api/v1/safelab/"


class SafeLabTestCase(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        self.sensor = Device.objects.get(pk="SENSOR-LAB002")
        self.node = APIClient()
        self.node.credentials(HTTP_AUTHORIZATION=f"Device {self.sensor.issue_key()}")
        User = get_user_model()
        self.student = APIClient()
        self.student.force_authenticate(User.objects.create_user("alice", password="unused-test-pw"))
        self.prof_user = User.objects.create_user("prof", password="unused-test-pw", is_staff=True)
        self.prof = APIClient()
        self.prof.force_authenticate(self.prof_user)

    def send(self, client=None, **values):
        return (client or self.node).post(TELEMETRY, values, format="json")

    def lab(self, lab_id="LAB002", client=None):
        labs = (client or self.student).get(DASHBOARD).json()["labs"]
        return next((lab for lab in labs if lab["labId"] == lab_id), None)


class TelemetryTests(SafeLabTestCase):
    def test_normal_reading_recorded(self):
        response = self.send(temperature_c=24.5, humidity_pct=48, gas_raw=600)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "recorded", "level": "normal",
                                           "message": "Electronics Lab: All readings normal", "alerts": []})
        reading = SensorReading.objects.get()
        self.assertEqual((reading.lab_id, reading.temperature_c, reading.gas_raw, reading.source),
                         ("LAB002", 24.5, 600, "device"))
        self.sensor.refresh_from_db()
        self.assertIsNotNone(self.sensor.last_seen_at)

    def test_levels_from_thresholds(self):
        self.assertEqual(self.send(temperature_c=33).json()["level"], "warning")
        self.assertEqual(self.send(temperature_c=41).json()["level"], "danger")
        self.assertEqual(self.send(temperature_c=8).json()["level"], "warning")
        self.assertEqual(self.send(humidity_pct=85).json()["level"], "warning")
        self.assertEqual(self.send(gas_raw=1600).json()["level"], "warning")
        body = self.send(temperature_c=25, gas_raw=3000).json()
        self.assertEqual(body["level"], "danger")
        self.assertIn("Gas sensor 3000 raw", body["alerts"][0])

    def test_partial_readings_are_fine(self):
        self.assertEqual(self.send(gas_raw=500).status_code, 201)
        self.assertEqual(self.send(temperature_c=None, humidity_pct=40).status_code, 201)

    def test_validation(self):
        for values in [{}, {"temperature_c": None}, {"temperature_c": "hot"}, {"temperature_c": 200},
                       {"humidity_pct": -5}, {"gas_raw": 5000}, {"gas_raw": True}]:
            response = self.node.post(TELEMETRY, values, format="json")
            self.assertEqual(response.status_code, 400, values)
            self.assertEqual(response.json()["status"], "error")
        response = self.node.post(TELEMETRY, "temperature_c=20", content_type="text/plain")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SensorReading.objects.exists())

    def test_needs_a_lab_sensor_key(self):
        self.assertEqual(self.send(client=APIClient(), temperature_c=20).status_code, 401)
        room = Device.objects.get(pk="READER-ROOM-101")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Device {room.issue_key()}")
        response = self.send(client=client, temperature_c=20)
        self.assertEqual(response.status_code, 400)
        self.assertIn("isn't assigned to a lab", response.json()["message"])


class AlertTests(SafeLabTestCase):
    def test_alert_opens_escalates_and_clears(self):
        self.send(gas_raw=1600)
        alert = SafetyAlert.objects.get()
        self.assertEqual((alert.kind, alert.level), ("gas", "warning"))

        self.send(gas_raw=2800)
        alert.refresh_from_db()
        self.assertEqual((alert.level, alert.value), ("danger", 2800))
        self.assertEqual(SafetyAlert.objects.count(), 1)

        self.send(gas_raw=1700)                  # still high, but an open alert is never downgraded
        alert.refresh_from_db()
        self.assertEqual(alert.level, "danger")

        self.send(gas_raw=400)
        alert.refresh_from_db()
        self.assertIsNotNone(alert.cleared_at)
        self.assertIsNone(alert.acknowledged_at)  # still needs faculty to acknowledge

    def test_unmeasured_kinds_dont_clear(self):
        self.send(temperature_c=41)
        self.send(gas_raw=300)                   # no temperature in this message
        self.assertIsNone(SafetyAlert.objects.get(kind="temperature").cleared_at)

    def test_one_alert_per_kind(self):
        self.send(temperature_c=41, gas_raw=3000)
        self.assertEqual(sorted(SafetyAlert.objects.values_list("kind", flat=True)), ["gas", "temperature"])
        alert = SafetyAlert.objects.get(kind="gas")
        with self.assertRaises(IntegrityError):
            SafetyAlert.objects.create(lab_id="LAB002", kind="gas", level="warning", message="x", value=1,
                                       last_seen_at=timezone.now())
        self.assertTrue(alert.pk)

    def test_faculty_acknowledge_and_new_alert_after(self):
        self.send(gas_raw=2600)
        alert = SafetyAlert.objects.get()
        url = f"/api/v1/safelab/alerts/{alert.id}/acknowledge/"
        self.assertEqual(self.student.post(url).status_code, 403)
        response = self.prof.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["acknowledgedBy"], "prof")
        alert.refresh_from_db()
        self.assertEqual(alert.acknowledged_by, self.prof_user)
        self.assertEqual(self.prof.post(url).status_code, 400)

        self.send(gas_raw=2600)                  # still dangerous: a fresh alert opens
        self.assertEqual(SafetyAlert.objects.filter(acknowledged_at__isnull=True).count(), 1)


class DashboardTests(SafeLabTestCase):
    def test_requires_sign_in(self):
        self.assertEqual(APIClient().get(DASHBOARD).status_code, 401)

    def test_live_lab_with_history_and_thresholds(self):
        self.send(temperature_c=24, humidity_pct=45, gas_raw=500)
        self.send(temperature_c=25, humidity_pct=46, gas_raw=520)
        body = self.student.get(DASHBOARD).json()
        self.assertEqual(body["thresholds"]["gasRaw"], {"warning_above": 1500, "danger_above": 2500})
        lab = self.lab()
        self.assertEqual((lab["labName"], lab["status"], lab["online"]), ("Electronics Lab", "normal", True))
        self.assertEqual(lab["latest"]["temperatureC"], 25)
        self.assertFalse(lab["latest"]["simulated"])
        self.assertEqual([r["gasRaw"] for r in lab["history"]], [500, 520])   # oldest first, for charts
        self.assertEqual(lab["sensors"][0]["id"], "SENSOR-LAB002")
        self.assertIsNone(self.lab("LAB001"))                                 # no sensor there

    def test_offline_and_unacknowledged_alerts_stay_visible(self):
        self.send(gas_raw=2600)
        SensorReading.objects.update(recorded_at=timezone.now() - timedelta(minutes=5))
        lab = self.lab()
        self.assertFalse(lab["online"])
        self.assertEqual(lab["status"], "danger")                             # open alert outranks "offline"
        self.assertEqual(lab["alerts"][0]["kind"], "gas")

        self.prof.post(f"/api/v1/safelab/alerts/{lab['alerts'][0]['id']}/acknowledge/")
        self.assertEqual(self.lab()["status"], "offline")

    def test_simulated_readings_are_labelled(self):
        call_command("simulate_reading", "SENSOR-LAB002", "--temp", "36", stdout=StringIO())
        lab = self.lab()
        self.assertTrue(lab["latest"]["simulated"])
        self.assertEqual(lab["status"], "warning")
        with self.assertRaises(CommandError):
            call_command("simulate_reading", "SENSOR-LAB002", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("simulate_reading", "READER-ROOM-101", "--temp", "20", stdout=StringIO())
