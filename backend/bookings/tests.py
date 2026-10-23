from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from labs.models import Lab

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
        self.assertEqual(body["status"], "active")
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
        self.assertEqual(self.book(lab="LAB002", hours=0).status_code, 201)

    def test_cancelled_booking_frees_the_slot(self):
        booking_id = self.book().json()["id"]
        self.assertEqual(self.client.post(f"{URL}{booking_id}/cancel/").status_code, 200)
        self.assertEqual(self.book().status_code, 201)

    # Visibility and cancellation

    def test_users_only_see_their_own_bookings(self):
        self.book()
        bob = APIClient()
        bob.force_authenticate(self.bob)
        self.book(lab="LAB002", client=bob)

        self.assertEqual([b["labID"] for b in self.client.get(URL).json()], ["LAB001"])
        self.assertEqual([b["labID"] for b in bob.get(URL).json()], ["LAB002"])

    def test_cannot_cancel_someone_elses_booking(self):
        booking_id = self.book().json()["id"]
        bob = APIClient()
        bob.force_authenticate(self.bob)
        self.assertEqual(bob.post(f"{URL}{booking_id}/cancel/").status_code, 404)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, "active")

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
