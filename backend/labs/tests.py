from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

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
            {"id", "name", "location", "symbol", "capacity", "equipment", "isOpenForBooking",
             "requiredCertifications"},
        )
        self.assertEqual(set(robotics["equipment"][0]),
                         {"id", "name", "category", "isAvailable", "requiredCertifications"})
        self.assertTrue(robotics["isOpenForBooking"])
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
