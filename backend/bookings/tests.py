from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from labs.models import Lab
from skillpass.models import UserCertification

from .models import Booking

URL = "/api/v1/bookings/"


class BookingApiTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.alice = User.objects.create_user("alice", password="unused-test-pw")
        self.bob = User.objects.create_user("bob", password="unused-test-pw")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        self.base = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)

    def at(self, hours):
        return (self.base + timedelta(hours=hours)).isoformat()

    def book(self, lab="LAB001", hours=0, minutes=60, client=None):
        return (client or self.client).post(
            URL, {"labID": lab, "start": self.at(hours), "durationMinutes": minutes}, format="json"
        )

    # Creating

    def test_create_booking_returns_ios_shape(self):
        response = self.book(minutes=120)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["labID"], "LAB001")
        self.assertEqual(body["labName"], "Robotics Lab")
        self.assertEqual(body["status"], "pending")      # Robotics Lab requires faculty approval
        booking = Booking.objects.get(pk=body["id"])
        self.assertEqual(booking.user, self.alice)
        self.assertEqual(booking.end - booking.start, timedelta(minutes=120))

    def test_requires_authentication(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get(URL).status_code, 401)
        self.assertEqual(self.book(client=anonymous).status_code, 401)

    def test_closed_lab_is_rejected(self):
        response = self.book(lab="LAB003")
        self.assertEqual(response.status_code, 400)
        self.assertIn("labID", response.json())

    def test_unknown_lab_is_404(self):
        self.assertEqual(self.book(lab="NOPE").status_code, 404)

    def test_past_start_is_rejected(self):
        response = self.client.post(
            URL,
            {"labID": "LAB001", "start": (timezone.now() - timedelta(hours=1)).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("start", response.json())

    def test_duration_limits(self):
        self.assertEqual(self.book(minutes=0).status_code, 400)
        self.assertEqual(self.book(minutes=10).status_code, 400)
        self.assertEqual(self.book(minutes=241).status_code, 400)
        self.assertEqual(self.book(minutes=240).status_code, 201)

    # Conflicts

    def test_overlap_in_same_lab_is_409_even_across_users(self):
        self.assertEqual(self.book(hours=0).status_code, 201)
        bob = APIClient()
        bob.force_authenticate(self.bob)
        response = self.client.post(
            URL, {"labID": "LAB001", "start": self.at(0.5)}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.book(hours=-0.5, minutes=120, client=bob).status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)

    def test_back_to_back_and_other_labs_are_allowed(self):
        self.assertEqual(self.book(hours=0).status_code, 201)
        self.assertEqual(self.book(hours=1).status_code, 201)
        self.assertEqual(self.book(hours=-1).status_code, 201)
        self.assertEqual(self.book(lab="LAB004", hours=0).status_code, 201)

    def test_cancelled_booking_frees_the_slot(self):
        booking_id = self.book().json()["id"]
        self.assertEqual(self.client.post(f"{URL}{booking_id}/cancel/").status_code, 200)
        self.assertEqual(self.book().status_code, 201)

    # Visibility and cancellation

    def test_users_only_see_their_own_bookings(self):
        self.book()
        bob = APIClient()
        bob.force_authenticate(self.bob)
        self.book(lab="LAB004", client=bob)

        self.assertEqual([b["labID"] for b in self.client.get(URL).json()], ["LAB001"])
        self.assertEqual([b["labID"] for b in bob.get(URL).json()], ["LAB004"])

    def test_cannot_cancel_someone_elses_booking(self):
        booking_id = self.book().json()["id"]
        bob = APIClient()
        bob.force_authenticate(self.bob)
        self.assertEqual(bob.post(f"{URL}{booking_id}/cancel/").status_code, 404)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, "pending")  # still held, not cancelled

    def test_cannot_cancel_twice(self):
        booking_id = self.book().json()["id"]
        self.client.post(f"{URL}{booking_id}/cancel/")
        self.assertEqual(self.client.post(f"{URL}{booking_id}/cancel/").status_code, 400)

    def test_cannot_cancel_finished_booking(self):
        past = Booking.objects.create(
            user=self.alice, lab=Lab.objects.get(pk="LAB001"),
            start=timezone.now() - timedelta(hours=2), end=timezone.now() - timedelta(hours=1),
        )
        self.assertEqual(self.client.post(f"{URL}{past.id}/cancel/").status_code, 400)

    # Database integrity

    def test_database_rejects_end_before_start(self):
        with self.assertRaises(IntegrityError):
            Booking.objects.create(
                user=self.alice, lab=Lab.objects.get(pk="LAB001"),
                start=self.base, end=self.base - timedelta(minutes=1),
            )


class ApprovalTests(TestCase):
    """Students' lab bookings wait for faculty approval when the lab requires it."""

    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.alice = User.objects.create_user("alice", first_name="Alice", last_name="Rao", password="unused-test-pw")
        self.bob = User.objects.create_user("bob", password="unused-test-pw")
        self.prof = User.objects.create_user("prof", first_name="Priya", last_name="Nair",
                                             password="unused-test-pw", is_staff=True)
        self.prof2 = User.objects.create_user("prof2", password="unused-test-pw", is_staff=True)
        self.student = self.api(self.alice)
        self.faculty = self.api(self.prof)
        self.base = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def api(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def request(self, client=None, lab="LAB001", hours=0, purpose="Build the robot chassis"):
        return (client or self.student).post(URL, {"labID": lab, "start": (self.base + timedelta(hours=hours)).isoformat(),
                                                   "durationMinutes": 60, "purpose": purpose}, format="json")

    def test_student_request_is_pending_with_purpose(self):
        body = self.request().json()
        self.assertEqual((body["status"], body["purpose"], body["student"]),
                         ("pending", "Build the robot chassis", "Alice Rao"))
        self.assertIsNone(body["decidedBy"])

    def test_labs_without_approval_confirm_immediately(self):
        Lab.objects.filter(pk="LAB004").update(requires_approval=False)
        self.assertEqual(self.request(lab="LAB004").json()["status"], "active")

    def test_staff_bookings_are_confirmed(self):
        self.assertEqual(self.request(client=self.faculty).json()["status"], "active")

    def test_pending_request_holds_the_slot(self):
        self.request()
        self.assertEqual(self.request(client=self.api(self.bob)).status_code, 409)

    def test_faculty_review_queue_and_approve(self):
        booking_id = self.request().json()["id"]
        self.assertEqual(self.student.get(URL + "?scope=pending").json()[0]["id"], booking_id)  # students: own list

        queue = self.faculty.get(URL + "?scope=pending").json()
        self.assertEqual([b["id"] for b in queue], [booking_id])
        response = self.faculty.post(f"{URL}{booking_id}/approve/", {"note": "Bring safety glasses"}, format="json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["status"], body["decidedBy"], body["decisionNote"]),
                         ("active", "Priya Nair", "Bring safety glasses"))
        self.assertEqual(self.faculty.get(URL + "?scope=pending").json(), [])
        self.assertEqual(self.student.get(URL).json()[0]["status"], "active")

    def test_decline_frees_the_slot(self):
        booking_id = self.request().json()["id"]
        body = self.faculty.post(f"{URL}{booking_id}/decline/", {"note": "Lab closed for maintenance"},
                                 format="json").json()
        self.assertEqual((body["status"], body["decisionNote"]), ("declined", "Lab closed for maintenance"))
        self.assertEqual(self.request(client=self.api(self.bob)).status_code, 201)

    def test_only_other_faculty_can_decide(self):
        booking_id = self.request().json()["id"]
        self.assertEqual(self.api(self.bob).post(f"{URL}{booking_id}/approve/").status_code, 404)
        self.assertEqual(self.student.post(f"{URL}{booking_id}/approve/").status_code, 403)
        Lab.objects.filter(pk="LAB002").update(requires_approval=True)
        own = Booking.objects.create(user=self.prof, lab_id="LAB004", start=self.base, end=self.base + timedelta(hours=1),
                                     status="pending")
        self.assertEqual(self.faculty.post(f"{URL}{own.id}/approve/").status_code, 403)
        self.assertEqual(self.api(self.prof2).post(f"{URL}{own.id}/approve/").status_code, 200)

    def test_cannot_decide_twice(self):
        booking_id = self.request().json()["id"]
        self.faculty.post(f"{URL}{booking_id}/approve/")
        self.assertEqual(self.faculty.post(f"{URL}{booking_id}/decline/").status_code, 400)

    def test_student_can_withdraw_request(self):
        booking_id = self.request().json()["id"]
        self.assertEqual(self.student.post(f"{URL}{booking_id}/cancel/").json()["status"], "cancelled")
        self.assertEqual(self.faculty.post(f"{URL}{booking_id}/approve/").status_code, 400)

    def test_unapproved_request_expires_at_start(self):
        booking = Booking.objects.create(user=self.alice, lab_id="LAB001", start=timezone.now() - timedelta(minutes=1),
                                         end=timezone.now() + timedelta(minutes=59), status="pending")
        response = self.faculty.post(f"{URL}{booking.id}/approve/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", response.json()["status"])
        booking.refresh_from_db()
        self.assertEqual(booking.status, "expired")

    def test_approval_rechecks_skillpass(self):
        UserCertification.objects.create(user=self.alice, certification_id="CERT-ELEC-BASIC", status="approved",
                                         approved_by=self.prof)
        booking_id = self.request(lab="LAB002").json()["id"]
        UserCertification.objects.filter(user=self.alice).update(status="revoked")
        response = self.faculty.post(f"{URL}{booking_id}/approve/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, "pending")

    def test_staff_default_list_is_their_own(self):
        self.request()
        self.assertEqual(self.faculty.get(URL).json(), [])
        self.assertEqual(len(self.faculty.get(URL + "?scope=all").json()), 1)
