import os
from datetime import datetime, time, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

REQUESTS = "/api/v1/requests/"


class RequestFlowTests(TestCase):
    """Student submits a lab booking and an equipment loan → admin sees both → approves/rejects → student sees it."""

    def setUp(self):
        with mock.patch.dict(os.environ, {"DEMO_STUDENT_PASSWORD": "unused-test-pw-1",
                                          "DEMO_ADMIN_PASSWORD": "unused-test-pw-2"}):
            call_command("seed_demo_accounts", stdout=StringIO())
        User = get_user_model()
        self.student = User.objects.get(username="demo_student")
        self.admin = User.objects.get(username="demo_admin")
        self.other = User.objects.create_user("other", password="unused-test-pw")

    @staticmethod
    def api(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def submit(self):
        day = timezone.localdate() + timedelta(days=2)
        start = timezone.make_aware(datetime.combine(day, time(10, 0)))
        booking = self.api(self.student).post("/api/v1/bookings/", {
            "labID": "LAB001", "start": start.isoformat(), "durationMinutes": 60, "purpose": "Robot chassis"},
            format="json")
        loan = self.api(self.student).post("/api/v1/inventory/loans/", {"equipmentId": "EQ008", "quantity": 2,
                                                                        "days": 3}, format="json")
        self.assertEqual((booking.status_code, loan.status_code), (201, 201))
        return booking.json(), loan.json(), start

    def test_admin_sees_all_pending_requests_from_both_modules(self):
        booking, loan, _ = self.submit()
        items = self.api(self.admin).get(REQUESTS).json()
        self.assertEqual({(i["type"], i["id"], i["status"]) for i in items},
                         {("lab_booking", booking["id"], "pending"), ("equipment", str(loan["id"]), "pending")})
        lab = next(i for i in items if i["type"] == "lab_booking")
        self.assertEqual((lab["title"], lab["requester"], lab["purpose"]), ("Robotics Lab", "Demo Student",
                                                                            "Robot chassis"))

    def test_approve_and_reject_update_the_students_requests(self):
        booking, loan, start = self.submit()
        admin = self.api(self.admin)
        self.assertEqual(admin.post(f"/api/v1/bookings/{booking['id']}/approve/").status_code, 200)
        self.assertEqual(admin.post(f"/api/v1/inventory/loans/{loan['id']}/reject/", {"note": "Out for repair"},
                                    format="json").status_code, 200)
        self.assertEqual(admin.get(REQUESTS).json(), [])   # nothing pending any more

        mine = {i["type"]: i for i in self.api(self.student).get(REQUESTS).json()}
        self.assertEqual((mine["lab_booking"]["status"], mine["lab_booking"]["decidedBy"]), ("approved", "Demo Admin"))
        self.assertEqual((mine["equipment"]["status"], mine["equipment"]["decisionNote"]), ("rejected", "Out for repair"))
        # Approved booking now holds the slot: another booking at the same time is refused.
        clash = self.api(self.other).post("/api/v1/bookings/", {"labID": "LAB001", "start": start.isoformat(),
                                                                "durationMinutes": 60}, format="json")
        self.assertEqual(clash.status_code, 409)
        # Rejected loan reserved nothing.
        arduino = next(i for i in APIClient().get("/api/v1/inventory/").json() if i["id"] == "EQ008")
        self.assertEqual(arduino["availableQuantity"], arduino["totalQuantity"])

    def test_lab_reject_with_reason(self):
        booking, _, _ = self.submit()
        self.api(self.admin).post(f"/api/v1/bookings/{booking['id']}/decline/", {"note": "Lab closed"}, format="json")
        lab = next(i for i in self.api(self.student).get(REQUESTS).json() if i["type"] == "lab_booking")
        self.assertEqual((lab["status"], lab["decisionNote"]), ("rejected", "Lab closed"))

    def test_students_only_see_their_own_and_cannot_decide(self):
        booking, loan, _ = self.submit()
        self.assertEqual(self.api(self.other).get(REQUESTS).json(), [])
        self.assertEqual(self.api(self.student).post(f"/api/v1/bookings/{booking['id']}/approve/").status_code, 403)
        self.assertEqual(self.api(self.student).post(f"/api/v1/inventory/loans/{loan['id']}/approve/").status_code, 403)
        self.assertEqual(APIClient().get(REQUESTS).status_code, 401)

    def test_status_filter(self):
        self.submit()
        self.assertEqual(len(self.api(self.student).get(REQUESTS, {"status": "pending"}).json()), 2)
        self.assertEqual(self.api(self.student).get(REQUESTS, {"status": "approved"}).json(), [])


class DemoAccountTests(TestCase):
    def test_roles_and_env_passwords(self):
        with mock.patch.dict(os.environ, {"DEMO_STUDENT_PASSWORD": "unused-test-pw-1",
                                          "DEMO_ADMIN_PASSWORD": "unused-test-pw-2"}):
            call_command("seed_demo_accounts", stdout=StringIO())
        User = get_user_model()
        student, admin = User.objects.get(username="demo_student"), User.objects.get(username="demo_admin")
        self.assertFalse(student.is_staff)
        self.assertTrue(admin.is_staff and admin.is_superuser)
        self.assertTrue(student.check_password("unused-test-pw-1"))
        self.assertTrue(admin.check_password("unused-test-pw-2"))
        me = APIClient()
        me.force_authenticate(admin)
        self.assertEqual(me.get("/api/v1/auth/me/").json()["role"], "administrator")

    def test_idempotent_and_never_resets_passwords_without_env(self):
        env = {k: v for k, v in os.environ.items() if k not in ("DEMO_STUDENT_PASSWORD", "DEMO_ADMIN_PASSWORD")}
        with mock.patch.dict(os.environ, env, clear=True):
            first = StringIO()
            call_command("seed_demo_accounts", stdout=first)
            self.assertIn("generated password", first.getvalue())
            hashed = get_user_model().objects.get(username="demo_admin").password
            second = StringIO()
            call_command("seed_demo_accounts", stdout=second)
        self.assertNotIn("generated password", second.getvalue())
        self.assertEqual(get_user_model().objects.get(username="demo_admin").password, hashed)
        self.assertEqual(get_user_model().objects.filter(username__startswith="demo_").count(), 2)
