import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from attendance.models import AttendanceRecord, AttendanceSession, CampusCard, Classroom
from attendance.reports import build_report
from bookings.models import Booking
from devices.models import Device
from inventory.models import EquipmentLoan
from safelab.models import SensorReading
from spaces.models import RoomBooking

from .models import Lab


class LabApiTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        self.client = APIClient()

    def test_health_is_public(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_lab_list_is_public_and_matches_ios_shape(self):
        response = self.client.get("/api/v1/labs/")
        self.assertEqual(response.status_code, 200)
        labs = response.json()
        self.assertEqual([lab["id"] for lab in labs], ["LAB001", "LAB002", "LAB003", "LAB004"])

        robotics = labs[0]
        self.assertEqual(
            set(robotics),
            {"id", "name", "location", "symbol", "capacity", "equipment", "isOpenForBooking", "requiresApproval",
             "requiredCertifications"},
        )
        self.assertEqual(set(robotics["equipment"][0]),
                         {"id", "name", "category", "isAvailable", "requiredCertifications"})
        self.assertTrue(robotics["isOpenForBooking"])
        self.assertTrue(robotics["requiresApproval"])
        self.assertFalse(labs[2]["isOpenForBooking"])
        self.assertEqual(robotics["requiredCertifications"], [])
        self.assertEqual(labs[1]["requiredCertifications"], ["CERT-ELEC-BASIC"])
        soldering = next(item for item in robotics["equipment"] if item["id"] == "EQ003")
        self.assertEqual(soldering["requiredCertifications"], ["CERT-SOLDER"])

    def test_lab_detail(self):
        response = self.client.get("/api/v1/labs/LAB002/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["equipment"]), 2)

    def test_labs_are_read_only(self):
        response = self.client.post("/api/v1/labs/", {"id": "X", "name": "X"}, format="json")
        self.assertEqual(response.status_code, 405)

    def test_seed_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Lab.objects.count(), 4)


class WalkthroughSeedTests(TestCase):
    def test_seed_then_clean_leaves_nothing_behind(self):
        with mock.patch.dict(os.environ, {"CAMPUSOS_WALKTHROUGH_PASSWORD": "unused-test-pw"}):
            call_command("seed_walkthrough", stdout=StringIO())
        self.assertEqual(get_user_model().objects.filter(username__startswith="demo_ui_").count(), 5)
        self.assertEqual(AttendanceRecord.objects.filter(session__classroom_id="DEMO-ROOM").count(), 3)
        demo_report = build_report(AttendanceSession.objects.get(classroom_id="DEMO-ROOM"))
        self.assertEqual((len(demo_report.present), len(demo_report.absent)), (3, 1))
        self.assertTrue(Device.objects.get(pk="READER-DEMO").key_hash)
        checked_in = Booking.objects.get(user__username="demo_ui_student", lab_id="LAB001")
        self.assertIsNotNone(checked_in.checked_in_at)
        self.assertEqual(checked_in.checked_in_device_id, "READER-DEMO-LAB")
        self.assertEqual(SensorReading.objects.filter(device_id="SENSOR-DEMO").count(), 7)
        self.assertTrue(EquipmentLoan.objects.filter(user__username="demo_ui_student").exists())
        self.assertTrue(RoomBooking.objects.filter(user__username="demo_ui_student").exists())

        call_command("seed_walkthrough", "--clean", stdout=StringIO())
        self.assertFalse(get_user_model().objects.filter(username__startswith="demo_ui_").exists())
        self.assertFalse(Classroom.objects.filter(pk="DEMO-ROOM").exists())
        self.assertFalse(Device.objects.filter(pk__in=["READER-DEMO", "READER-DEMO-LAB", "SENSOR-DEMO"]).exists())
        self.assertFalse(SensorReading.objects.exists())
        self.assertFalse(EquipmentLoan.objects.exists())
        self.assertFalse(RoomBooking.objects.exists())
        self.assertTrue(Device.objects.filter(pk="READER-LAB001").exists())  # real readers kept
        self.assertTrue(Lab.objects.exists())  # real catalogue kept

    def test_refuses_to_take_over_a_real_card(self):
        real = get_user_model().objects.create_user("real_student", password="unused-test-pw")
        CampusCard.objects.create(uid="D1D1D1D1", user=real)
        with mock.patch.dict(os.environ, {"CAMPUSOS_WALKTHROUGH_PASSWORD": "unused-test-pw"}):
            with self.assertRaises(CommandError):
                call_command("seed_walkthrough", stdout=StringIO())
        self.assertEqual(CampusCard.objects.get(uid="D1D1D1D1").user, real)

    def test_requires_password(self):
        with mock.patch.dict(os.environ, {"CAMPUSOS_WALKTHROUGH_PASSWORD": ""}):
            with self.assertRaises(CommandError):
                call_command("seed_walkthrough", stdout=StringIO())
