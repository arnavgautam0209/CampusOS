from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.models import AttendanceSession

from . import services
from .models import RoomBooking

SPACES = "/api/v1/spaces/"
BOOKINGS = "/api/v1/spaces/bookings/"


class SpacesTestCase(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.alice = User.objects.create_user("alice", first_name="Alice", last_name="Rao", password="unused-test-pw")
        self.bob = User.objects.create_user("bob", password="unused-test-pw")
        self.prof = User.objects.create_user("prof", password="unused-test-pw", is_staff=True)
        self.client = self.api(self.alice)
        self.tomorrow = timezone.localdate() + timedelta(days=1)

    @staticmethod
    def api(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def at(self, hour, minute=0, day=None):
        return timezone.make_aware(datetime.combine(day or self.tomorrow, time(hour, minute)))

    def book(self, room="STUDY-A1", hour=10, minutes=60, attendees=3, client=None, **extra):
        body = {"roomId": room, "start": self.at(hour).isoformat(), "durationMinutes": minutes,
                "attendees": attendees, "purpose": "Group study"}
        body.update(extra)
        return (client or self.client).post(BOOKINGS, body, format="json")

    def room(self, room_id, client=None, day=None):
        url = SPACES + (f"?date={day.isoformat()}" if day else "")
        rooms = (client or self.client).get(url).json()["rooms"]
        return next(r for r in rooms if r["id"] == room_id)


class AvailabilityTests(SpacesTestCase):
    def test_requires_sign_in(self):
        self.assertEqual(APIClient().get(SPACES).status_code, 401)

    def test_lists_rooms_with_details(self):
        body = self.client.get(SPACES).json()
        self.assertEqual(body["date"], timezone.localdate().isoformat())
        study = self.room("STUDY-A1")
        self.assertEqual(
            {k: study[k] for k in ["name", "kind", "capacity", "location", "features", "isBookable", "freeNow"]},
            {"name": "Study Room A1", "kind": "study_room", "capacity": 6, "location": "Library · Level 1",
             "features": ["Whiteboard", "TV screen"], "isBookable": True, "freeNow": True},
        )
        self.assertFalse(self.room("ROOM-101")["isBookable"])           # timetabled for students
        self.assertTrue(self.room("ROOM-101", client=self.api(self.prof))["isBookable"])

    def test_busy_slots_hide_who_booked_from_students(self):
        self.book(client=self.api(self.bob))
        self.book(hour=13)
        slots = self.room("STUDY-A1", day=self.tomorrow)["busy"]
        self.assertEqual([(s["mine"], s["bookedBy"]) for s in slots], [(False, None), (True, None)])
        staff_view = self.room("STUDY-A1", client=self.api(self.prof), day=self.tomorrow)["busy"]
        self.assertEqual([s["bookedBy"] for s in staff_view], ["bob", "Alice Rao"])

    def test_in_class_now_from_attendance_session(self):
        AttendanceSession.objects.create(classroom_id="ROOM-101", title="Lecture")
        room = self.room("ROOM-101")
        self.assertTrue(room["inClassNow"])
        self.assertFalse(room["freeNow"])

    def test_date_validation(self):
        self.assertEqual(self.client.get(SPACES + "?date=nope").status_code, 400)
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(self.client.get(SPACES + f"?date={past}").status_code, 400)


class BookingRuleTests(SpacesTestCase):
    def test_book_study_room(self):
        response = self.book()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["roomId"], body["attendees"], body["status"], body["purpose"]),
                         ("STUDY-A1", 3, "active", "Group study"))

    def test_overlap_is_409_but_back_to_back_is_fine(self):
        self.book()
        clash = self.book(hour=10, minutes=30, client=self.api(self.bob))
        self.assertEqual(clash.status_code, 409)
        self.assertEqual(self.book(hour=11, client=self.api(self.bob)).status_code, 201)
        self.assertEqual(self.book(room="STUDY-A2", hour=10, client=self.api(self.bob)).status_code, 201)

    def test_capacity(self):
        response = self.book(room="STUDY-A2", attendees=5)
        self.assertEqual(response.status_code, 400)
        self.assertIn("seats 4", response.json()["attendees"])

    def test_timetabled_classroom_staff_only(self):
        self.assertEqual(self.book(room="ROOM-101").status_code, 403)
        self.assertEqual(self.book(room="ROOM-101", client=self.api(self.prof)).status_code, 201)

    def test_validation(self):
        self.assertEqual(self.book(minutes=10).status_code, 400)
        self.assertEqual(self.book(minutes=300).status_code, 400)
        self.assertEqual(self.book(attendees=0).status_code, 400)
        self.assertEqual(self.book(attendees=True).status_code, 400)
        self.assertEqual(self.book(room="NOPE").status_code, 404)
        past = self.client.post(BOOKINGS, {"roomId": "STUDY-A1", "start": (timezone.now() - timedelta(hours=1))
                                           .isoformat()}, format="json")
        self.assertEqual(past.status_code, 400)
        far = self.client.post(BOOKINGS, {"roomId": "STUDY-A1", "start": (timezone.now() + timedelta(days=40))
                                          .isoformat()}, format="json")
        self.assertEqual(far.status_code, 400)
        self.assertFalse(RoomBooking.objects.exists())

    def test_cancelled_booking_frees_the_room(self):
        booking_id = self.book().json()["id"]
        self.assertEqual(self.client.post(f"{BOOKINGS}{booking_id}/cancel/").status_code, 200)
        self.assertEqual(self.book(client=self.api(self.bob)).status_code, 201)

    def test_only_owner_or_staff_can_cancel(self):
        booking_id = self.book().json()["id"]
        self.assertEqual(self.api(self.bob).post(f"{BOOKINGS}{booking_id}/cancel/").status_code, 404)
        self.assertEqual(self.api(self.prof).post(f"{BOOKINGS}{booking_id}/cancel/").status_code, 200)

    def test_database_constraints(self):
        with self.assertRaises(IntegrityError):
            RoomBooking.objects.create(room_id="STUDY-A1", user=self.alice, start=self.at(10), end=self.at(9))


class CheckInAndNoShowTests(SpacesTestCase):
    def soon_booking(self, starts_in_minutes):
        start = timezone.now() + timedelta(minutes=starts_in_minutes)
        return RoomBooking.objects.create(room_id="STUDY-A1", user=self.alice, start=start,
                                          end=start + timedelta(hours=1))

    def test_check_in_window(self):
        early = self.soon_booking(30)
        response = self.client.post(f"{BOOKINGS}{early.id}/check-in/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Check-in opens at", response.json()["status"])

        booking = self.soon_booking(5)
        response = self.client.post(f"{BOOKINGS}{booking.id}/check-in/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["checkedInAt"])

    def test_no_show_expires_and_frees_room(self):
        late = self.soon_booking(-20)                       # started 20 minutes ago, nobody came
        services.release_no_shows()
        late.refresh_from_db()
        self.assertEqual(late.status, "expired")
        response = self.client.post(f"{BOOKINGS}{late.id}/check-in/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("released", response.json()["status"])
        self.assertTrue(self.room("STUDY-A1")["freeNow"])

    def test_checked_in_booking_is_never_expired(self):
        booking = self.soon_booking(-20)
        booking.checked_in_at = booking.start
        booking.save()
        services.release_no_shows()
        booking.refresh_from_db()
        self.assertEqual(booking.status, "active")
        self.assertFalse(self.room("STUDY-A1")["freeNow"])

    def test_only_the_booker_checks_in(self):
        booking = self.soon_booking(5)
        self.assertEqual(self.api(self.bob).post(f"{BOOKINGS}{booking.id}/check-in/").status_code, 404)
        self.assertEqual(self.api(self.prof).post(f"{BOOKINGS}{booking.id}/check-in/").status_code, 403)


class ListAndUtilizationTests(SpacesTestCase):
    def test_my_bookings_and_staff_scope(self):
        self.book()
        self.book(room="STUDY-A2", client=self.api(self.bob))
        self.assertEqual([b["roomId"] for b in self.client.get(BOOKINGS).json()], ["STUDY-A1"])
        everyone = self.api(self.prof).get(BOOKINGS + "?scope=all").json()
        self.assertEqual(sorted(b["roomId"] for b in everyone), ["STUDY-A1", "STUDY-A2"])

    def test_utilization_staff_only(self):
        self.assertEqual(self.client.get("/api/v1/spaces/utilization/").status_code, 403)
        start = timezone.now() - timedelta(days=1)
        RoomBooking.objects.create(room_id="MEET-B2", user=self.alice, start=start, end=start + timedelta(hours=3),
                                   checked_in_at=start)
        RoomBooking.objects.create(room_id="MEET-B2", user=self.bob, start=start + timedelta(hours=4),
                                   end=start + timedelta(hours=5))   # nobody checked in: becomes a no-show
        rows = self.api(self.prof).get("/api/v1/spaces/utilization/?days=7").json()["rooms"]
        meet = next(r for r in rows if r["roomId"] == "MEET-B2")
        self.assertEqual((meet["bookings"], meet["noShows"], meet["bookedHours"]), (2, 1, 3.0))
        self.assertEqual(meet["utilizationPct"], round(100 * 3 / (7 * 12)))
