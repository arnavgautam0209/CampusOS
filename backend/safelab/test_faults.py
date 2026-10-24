from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from labs.models import Equipment

from .models import EquipmentFault

FAULTS = "/api/v1/safelab/faults/"


class FaultTestCase(TestCase):
    def setUp(self):
        call_command("seed_safelab_demo", stdout=StringIO())
        User = get_user_model()
        self.student = User.objects.create_user("stu", first_name="Sam", last_name="Lee", password="unused-test-pw")
        self.other = User.objects.create_user("other", password="unused-test-pw")
        self.prof = User.objects.create_user("prof", first_name="Priya", last_name="Nair", password="unused-test-pw",
                                             is_staff=True)

    @staticmethod
    def api(user=None):
        client = APIClient()
        if user:
            client.force_authenticate(user)
        return client

    def report(self, user=None, **overrides):
        body = {"labId": "LAB005", "equipmentId": "MAC-IMAC-02", "category": "not_working", "severity": "high",
                "description": "Won't boot past the Apple logo."}
        body.update(overrides)
        return self.api(user or self.student).post(FAULTS, body, format="json")

    def act(self, fault_id, action, note="", user=None):
        return self.api(user or self.prof).post(f"{FAULTS}{fault_id}/{action}/", {"note": note}, format="json")


class SeedTests(FaultTestCase):
    def test_labs_list_only_their_own_equipment_with_asset_ids(self):
        labs = {lab["id"]: lab for lab in self.api(self.student).get("/api/v1/safelab/labs/").json()}
        self.assertEqual(labs["LAB005"]["name"], "Mac Lab")
        self.assertEqual(labs["LAB006"]["name"], "IoT Lab")
        mac = {e["id"]: e["name"] for e in labs["LAB005"]["equipment"]}
        self.assertEqual(sorted(mac.values()), ["External Monitor", "Magic Keyboard", "Magic Mouse", "Projector",
                                                "USB-C Hub", "iMac 01", "iMac 02", "iMac 03"])
        self.assertTrue(all(e["id"] for lab in labs.values() for e in lab["equipment"]))
        self.assertNotIn("Arduino Uno", mac.values())

    def test_rerun_adds_nothing(self):
        before = (Equipment.objects.count(), EquipmentFault.objects.count())
        call_command("seed_safelab_demo", stdout=StringIO())
        self.assertEqual((Equipment.objects.count(), EquipmentFault.objects.count()), before)


class ReportTests(FaultTestCase):
    def test_student_reports_existing_equipment_as_pending(self):
        response = self.report()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["status"], body["labName"], body["equipmentName"], body["equipmentId"]),
                         ("pending", "Mac Lab", "iMac 02", "MAC-IMAC-02"))
        mine = self.api(self.student).get(FAULTS).json()
        self.assertEqual([f["id"] for f in mine], [body["id"]])   # only their own reports
        self.assertEqual(self.api(self.other).get(FAULTS).json(), [])

    def test_equipment_must_belong_to_the_chosen_lab(self):
        response = self.report(labId="LAB005", equipmentId="IOT-ARD-01")
        self.assertEqual(response.status_code, 400)
        self.assertIn("isn't in Mac Lab", response.json()["equipmentId"])
        self.assertEqual(self.report(labId="LAB006", equipmentId="IOT-ARD-01").status_code, 201)

    def test_free_text_or_unknown_equipment_is_rejected(self):
        self.assertEqual(self.report(equipmentId="My broken chair").status_code, 400)
        self.assertEqual(self.report(labId="").status_code, 400)

    def test_category_severity_and_description_are_required(self):
        response = self.report(category="wifi_complaint", severity="urgent", description="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"category", "severity", "description"})
        for category in ["not_working", "partially_working", "physically_damaged", "unexpected_behaviour", "other"]:
            self.assertEqual(self.report(category=category).status_code, 201, category)

    def test_requires_sign_in(self):
        self.assertEqual(self.api().post(FAULTS, {}, format="json").status_code, 401)


class ReviewTests(FaultTestCase):
    def test_faculty_see_all_reports_with_details(self):
        mine = self.report().json()
        rows = self.api(self.prof).get(FAULTS, {"status": "pending"}).json()
        row = next(r for r in rows if r["id"] == mine["id"])
        self.assertEqual((row["labName"], row["equipmentId"], row["reporter"], row["categoryLabel"], row["severity"]),
                         ("Mac Lab", "MAC-IMAC-02", "Sam Lee", "Not Working", "high"))

    def test_approve_maintenance_resolve_updates_student_view_and_equipment(self):
        fault = self.report().json()
        self.assertEqual(self.act(fault["id"], "approve").json()["status"], "approved")
        self.assertEqual(self.act(fault["id"], "maintenance", "Sent to Apple service").json()["status"],
                         "under_maintenance")
        self.assertFalse(Equipment.objects.get(pk="MAC-IMAC-02").is_available)
        self.assertEqual(self.act(fault["id"], "resolve", "Logic board replaced").json()["status"], "resolved")
        self.assertTrue(Equipment.objects.get(pk="MAC-IMAC-02").is_available)
        mine = self.api(self.student).get(FAULTS).json()[0]
        self.assertEqual((mine["status"], mine["decisionNote"], mine["decidedBy"]),
                         ("resolved", "Logic board replaced", "Priya Nair"))

    def test_reject_needs_a_reason(self):
        fault = self.report().json()
        self.assertEqual(self.act(fault["id"], "reject").status_code, 400)
        response = self.act(fault["id"], "reject", "Monitor cable was unplugged")
        self.assertEqual((response.json()["status"], response.json()["decisionNote"]),
                         ("rejected", "Monitor cable was unplugged"))
        self.assertEqual(self.act(fault["id"], "approve").status_code, 400)   # already decided

    def test_invalid_transitions_and_actions(self):
        fault = self.report().json()
        self.assertEqual(self.act(fault["id"], "resolve").status_code, 400)    # pending can't jump to resolved
        self.assertEqual(self.act(fault["id"], "delete").status_code, 400)

    def test_students_cannot_review_or_see_analytics(self):
        fault = self.report().json()
        self.assertEqual(self.act(fault["id"], "approve", user=self.student).status_code, 403)
        self.assertEqual(self.api(self.student).get(FAULTS + "analytics/").status_code, 403)
        self.assertEqual(EquipmentFault.objects.get(pk=fault["id"]).status, "pending")


class AnalyticsTests(FaultTestCase):
    def test_counts_come_from_the_database(self):
        before = self.api(self.prof).get(FAULTS + "analytics/").json()
        self.assertEqual(before["total"], 26)
        self.assertEqual(len(before["monthly"]), 6)
        self.assertEqual(sum(m["count"] for m in before["monthly"]), 26)
        # iMac 01 and the ESP32 board both have 3 non-rejected reports; ties sort by asset ID.
        self.assertEqual([(r["label"], r["count"]) for r in before["mostReported"][:2]],
                         [("ESP32 Development Board", 3), ("iMac 01", 3)])
        statuses = {s["key"]: s["count"] for s in before["byStatus"]}
        self.assertEqual(statuses, {"pending": 4, "approved": 3, "rejected": 3, "under_maintenance": 1,
                                    "resolved": 15})

        self.report(labId="LAB006", equipmentId="IOT-ESP32-01")
        after = self.api(self.prof).get(FAULTS + "analytics/").json()
        self.assertEqual(after["total"], 27)
        self.assertEqual(after["monthly"][-1]["count"], before["monthly"][-1]["count"] + 1)
        labs = {row["key"]: row["count"] for row in after["byLab"]}
        before_labs = {row["key"]: row["count"] for row in before["byLab"]}
        self.assertEqual(labs["LAB006"], before_labs["LAB006"] + 1)
        types = {row["key"]: row["count"] for row in after["byEquipmentType"]}
        self.assertNotIn("Temperature", types)   # equipment types only

    def test_rejected_reports_are_not_counted_as_faults(self):
        fault = self.report(equipmentId="MAC-IMAC-03").json()
        self.act(fault["id"], "reject", "Not a fault")
        data = self.api(self.prof).get(FAULTS + "analytics/").json()
        imac3 = next((r for r in data["mostReported"] if r["key"] == "MAC-IMAC-03"), {"count": 1})
        self.assertEqual(imac3["count"], 1)
