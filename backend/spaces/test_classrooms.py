from datetime import datetime, time, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.models import Classroom

from . import services
from .models import RoomBooking, Timetable, TimetableEvent

AVAILABILITY = "/api/v1/spaces/availability/"
BOOKINGS = "/api/v1/spaces/bookings/"
TIMETABLES = "/api/v1/spaces/timetables/"
DEMO_DIR = "demo_data/spacepulse/"


def read(name):
    with open(DEMO_DIR + name, encoding="utf-8") as handle:
        return handle.read()


def next_weekday(weekday):
    """The next given weekday at least one day from today (bookings must be in the future)."""
    day = timezone.localdate() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


MONDAY, TUESDAY = 0, 1


class ClassroomTestCase(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_spacepulse_demo", stdout=StringIO())
        User = get_user_model()
        self.alice = User.objects.create_user("alice", first_name="Alice", last_name="Rao", password="unused-test-pw")
        self.bob = User.objects.create_user("bob", password="unused-test-pw")
        self.carol = User.objects.create_user("carol", password="unused-test-pw")
        self.prof = User.objects.create_user("prof", first_name="Priya", last_name="Nair", password="unused-test-pw",
                                             is_staff=True)
        self.monday, self.tuesday = next_weekday(MONDAY), next_weekday(TUESDAY)

    @staticmethod
    def api(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def at(self, day, hour, minute=0):
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    def book(self, user, room, day, hour, minute=0, minutes=60, group=8, mode="shared"):
        return self.api(user).post(BOOKINGS, {
            "roomId": room, "start": self.at(day, hour, minute).isoformat(), "durationMinutes": minutes,
            "attendees": group, "mode": mode, "purpose": "Group study"}, format="json")

    def find(self, day, start, group=1, minutes=60, mode="shared", user=None):
        response = self.api(user or self.alice).get(AVAILABILITY, {
            "date": day.isoformat(), "start": start, "duration": minutes, "group_size": group, "mode": mode})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def seats(self, room, day, start, minutes=60):
        body = self.find(day, start, minutes=minutes)
        for row in body["rooms"] + body["unavailable"]:
            if row["id"] == room:
                return row["availableSeats"]
        raise AssertionError(f"{room} not listed")

    def upload(self, csv_text, name="Timetable B — Revised", filename="Timetable_B_Updated.csv", user=None):
        return self.api(user or self.prof).post(TIMETABLES + "upload/", {
            "name": name, "filename": filename, "csv": csv_text}, format="json")


class SeedTests(ClassroomTestCase):
    def test_six_fictional_classrooms_in_the_database(self):
        rooms = dict(Classroom.objects.filter(id__in=["ECE-101", "ECE-102", "IT-201", "CSE-301", "SEM-01", "HALL-01"])
                     .values_list("id", "capacity"))
        self.assertEqual(rooms, {"ECE-101": 30, "ECE-102": 45, "IT-201": 60, "CSE-301": 75, "SEM-01": 100,
                                 "HALL-01": 150})

    def test_timetable_a_is_active_and_b_is_not_loaded(self):
        active = Timetable.objects.get(status=Timetable.Status.ACTIVE)
        self.assertEqual(active.source_filename, "Timetable_A_Initial.csv")
        self.assertEqual(active.entries.count(), 18)
        self.assertEqual(Timetable.objects.count(), 1)

    def test_rerunning_seed_changes_nothing(self):
        call_command("seed_spacepulse_demo", stdout=StringIO())
        self.assertEqual(Timetable.objects.count(), 1)
        self.assertEqual(Classroom.objects.filter(id="IT-201").count(), 1)

    def test_seed_never_replaces_an_uploaded_active_timetable(self):
        b = Timetable.objects.get(pk=self.upload(read("Timetable_B_Updated.csv")).json()["id"])
        self.assertEqual(self.api(self.prof).post(f"{TIMETABLES}{b.id}/activate/").status_code, 200)
        call_command("seed_spacepulse_demo", stdout=StringIO())
        self.assertEqual(Timetable.objects.get(status=Timetable.Status.ACTIVE).pk, b.pk)

    def test_seed_keeps_an_existing_room_as_it_is(self):
        Classroom.objects.filter(pk="IT-201").update(capacity=64)
        call_command("seed_spacepulse_demo", stdout=StringIO())
        self.assertEqual(Classroom.objects.get(pk="IT-201").capacity, 64)


class SharedSeatTests(ClassroomTestCase):
    """IT-201 (60 seats) is free on Monday 14:00–15:00 in both timetables."""

    def test_group_of_8_leaves_52_then_12_more_leaves_40_and_cancel_restores(self):
        self.assertEqual(self.seats("IT-201", self.monday, "14:00"), 60)
        first = self.book(self.alice, "IT-201", self.monday, 14, group=8)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["mode"], "shared")
        self.assertEqual(self.seats("IT-201", self.monday, "14:00"), 52)

        self.assertEqual(self.book(self.bob, "IT-201", self.monday, 14, group=12).status_code, 201)
        self.assertEqual(self.seats("IT-201", self.monday, "14:00"), 40)

        cancelled = self.api(self.alice).post(f"{BOOKINGS}{first.json()['id']}/cancel/")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(self.seats("IT-201", self.monday, "14:00"), 48)
        # Capacity itself never changes.
        self.assertEqual(Classroom.objects.get(pk="IT-201").capacity, 60)

    def test_group_larger_than_remaining_seats_is_rejected(self):
        self.book(self.alice, "IT-201", self.monday, 14, group=8)
        self.book(self.bob, "IT-201", self.monday, 14, group=12)
        response = self.book(self.carol, "IT-201", self.monday, 14, group=45)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Only 40 of 60 seats", response.json()["detail"])
        self.assertEqual(self.book(self.carol, "IT-201", self.monday, 14, group=40).status_code, 201)
        self.assertEqual(self.book(self.carol, "IT-201", self.monday, 14, group=1).status_code, 409)

    def test_peak_concurrent_seats_over_overlapping_intervals(self):
        # IT-201 on Tuesday: only a 09:00 class. Group A 8 seats 11:00–12:00, group B 12 seats 11:30–12:30.
        self.assertEqual(self.book(self.alice, "IT-201", self.tuesday, 11, group=8).status_code, 201)
        self.assertEqual(self.book(self.bob, "IT-201", self.tuesday, 11, 30, group=12).status_code, 201)
        self.assertEqual(self.seats("IT-201", self.tuesday, "11:00", minutes=30), 52)
        self.assertEqual(self.seats("IT-201", self.tuesday, "11:30", minutes=30), 40)
        self.assertEqual(self.seats("IT-201", self.tuesday, "12:00", minutes=30), 48)
        self.assertEqual(self.seats("IT-201", self.tuesday, "12:30", minutes=30), 60)
        # Group C 11:15–12:15 must fit the busiest moment (40 free), not just its start time.
        self.assertEqual(self.seats("IT-201", self.tuesday, "11:15"), 40)
        self.assertEqual(self.book(self.carol, "IT-201", self.tuesday, 11, 15, group=41).status_code, 409)
        self.assertEqual(self.book(self.carol, "IT-201", self.tuesday, 11, 15, group=40).status_code, 201)

    def test_non_overlapping_bookings_do_not_reduce_seats(self):
        self.book(self.alice, "IT-201", self.tuesday, 10, group=50)    # 10:00–11:00
        self.book(self.bob, "IT-201", self.tuesday, 12, group=50)      # 12:00–13:00
        self.assertEqual(self.seats("IT-201", self.tuesday, "11:00"), 60)   # touching ends don't overlap

    def test_cancelled_and_expired_bookings_take_no_seats(self):
        booking = self.book(self.alice, "IT-201", self.tuesday, 11, group=30).json()
        RoomBooking.objects.filter(pk=booking["id"]).update(status=RoomBooking.Status.EXPIRED)
        self.assertEqual(self.seats("IT-201", self.tuesday, "11:00"), 60)

    def test_exclusive_booking_blocks_sharing_and_vice_versa(self):
        self.assertEqual(self.book(self.alice, "ECE-102", self.tuesday, 11, group=5, mode="exclusive").status_code, 201)
        self.assertEqual(self.seats("ECE-102", self.tuesday, "11:00"), 0)
        self.assertEqual(self.book(self.bob, "ECE-102", self.tuesday, 11, group=2).status_code, 409)
        self.book(self.bob, "SEM-01", self.tuesday, 11, group=2)
        self.assertEqual(self.book(self.carol, "SEM-01", self.tuesday, 11, group=5, mode="exclusive").status_code, 409)

    def test_booking_without_mode_stays_exclusive_for_existing_clients(self):
        response = self.api(self.alice).post(BOOKINGS, {"roomId": "STUDY-A1", "start": self.at(self.tuesday, 11)
                                                        .isoformat(), "durationMinutes": 60, "attendees": 3},
                                             format="json")
        self.assertEqual(response.json()["mode"], "exclusive")

    def test_invalid_group_sizes_are_rejected(self):
        self.assertEqual(self.book(self.alice, "IT-201", self.monday, 14, group=0).status_code, 400)
        self.assertEqual(self.book(self.alice, "IT-201", self.monday, 14, group=61).status_code, 400)
        self.assertEqual(self.api(self.alice).get(AVAILABILITY, {"date": self.monday.isoformat(), "start": "11:00",
                                                                 "group_size": "eight"}).status_code, 400)


class TimetableBlockingTests(ClassroomTestCase):
    def test_scheduled_lecture_blocks_the_whole_room(self):
        response = self.book(self.alice, "IT-201", self.monday, 11, group=1)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Python Programming", response.json()["detail"])
        body = self.find(self.monday, "11:00", group=1)
        it = next(r for r in body["unavailable"] if r["id"] == "IT-201")
        self.assertEqual(it["availableSeats"], 0)
        self.assertEqual(it["reason"], "Timetabled: Python Programming 11:00–12:00")

    def test_partial_overlap_with_a_lecture_blocks(self):
        # 10:30–11:30 overlaps the 11:00 class.
        self.assertEqual(self.book(self.alice, "IT-201", self.monday, 10, 30, group=1).status_code, 409)
        self.assertEqual(self.book(self.alice, "IT-201", self.monday, 10, 0, group=1).status_code, 201)

    def test_day_view_lists_lectures(self):
        rooms = self.api(self.alice).get("/api/v1/spaces/", {"date": self.monday.isoformat()}).json()["rooms"]
        it = next(r for r in rooms if r["id"] == "IT-201")
        self.assertEqual([l["activity"] for l in it["lectures"]], ["Python Programming"])


class RecommendationTests(ClassroomTestCase):
    def test_smallest_suitable_room_is_recommended(self):
        body = self.find(self.monday, "11:00", group=8)
        self.assertEqual(body["recommended"]["id"], "ECE-101")
        self.assertEqual(body["message"], "Best fit for 8 people — 22 seats would remain available.")
        self.assertEqual([(r["id"], r["availableSeats"], r["seatsAfterBooking"]) for r in body["rooms"]],
                         [("ECE-101", 30, 22), ("ECE-102", 45, 37), ("CSE-301", 75, 67), ("SEM-01", 100, 92),
                          ("HALL-01", 150, 142)])
        self.assertEqual(body["timetable"]["version"], 1)

    def test_uses_free_seats_not_total_capacity(self):
        self.book(self.bob, "ECE-101", self.monday, 11, group=25)        # 5 left in ECE-101
        body = self.find(self.monday, "11:00", group=8)
        self.assertEqual(body["recommended"]["id"], "ECE-102")
        ece101 = next(r for r in body["unavailable"] if r["id"] == "ECE-101")
        self.assertEqual((ece101["availableSeats"], ece101["reason"]), (5, "Only 5 seats free then"))

    def test_no_room_available_says_so(self):
        body = self.find(self.monday, "11:00", group=200)
        self.assertIsNone(body["recommended"])
        self.assertEqual(body["rooms"], [])
        self.assertIn("No room has 200 seats free for the whole of 11:00–12:00", body["message"])

    def test_students_only_see_rooms_they_may_book(self):
        ids = {r["id"] for r in self.find(self.monday, "16:00", group=1)["rooms"]}
        self.assertNotIn("ROOM-101", ids)      # timetabled AttendX room, not student-bookable
        self.assertIn("IT-201", ids)

    def test_numbers_come_from_the_database(self):
        Classroom.objects.filter(pk="ECE-101").update(capacity=10)
        body = self.find(self.monday, "11:00", group=8)
        self.assertEqual((body["recommended"]["id"], body["recommended"]["seatsAfterBooking"]), ("ECE-101", 2))


class UploadTests(ClassroomTestCase):
    def test_student_cannot_upload_or_activate(self):
        self.assertEqual(self.upload(read("Timetable_B_Updated.csv"), user=self.alice).status_code, 403)
        a = Timetable.objects.get()
        self.assertEqual(self.api(self.alice).post(f"{TIMETABLES}{a.id}/activate/").status_code, 403)
        self.assertEqual(self.api(self.alice).get(TIMETABLES).status_code, 403)
        self.assertEqual(self.api(self.alice).get(TIMETABLES + "active/").status_code, 200)   # reading is fine
        self.assertEqual(APIClient().get(TIMETABLES + "active/").status_code, 401)

    def test_faculty_upload_creates_a_draft_with_preview(self):
        response = self.upload(read("Timetable_B_Updated.csv"))
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["status"], body["version"], body["classCount"]), ("draft", 2, 19))
        changes = {(c["day"], c["start"], c["roomId"], c["change"]) for c in body["preview"]["changes"]}
        self.assertEqual(changes, {("Monday", "11:00", "ECE-101", "occupied"), ("Monday", "11:00", "CSE-301", "occupied"),
                                   ("Monday", "15:00", "ECE-102", "freed"),
                                   ("Friday", "11:00", "IT-201", "activity_changed")})
        # Uploading alone changes nothing for students.
        self.assertEqual(self.find(self.monday, "11:00", group=8)["recommended"]["id"], "ECE-101")
        self.assertTrue(TimetableEvent.objects.filter(action="uploaded", timetable_id=body["id"]).exists())

    def test_multipart_file_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile("Timetable_B_Updated.csv", read("Timetable_B_Updated.csv").encode())
        response = self.api(self.prof).post(TIMETABLES + "upload/", {"file": upload, "name": "B"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["sourceFilename"], "Timetable_B_Updated.csv")

    def test_invalid_rows_are_rejected_with_line_numbers(self):
        bad = ("day,start,end,room_id,activity\n"
               "Monday,09:00,10:00,ECE-101,Digital Electronics\n"
               "Funday,09:00,10:00,ECE-101,Nope\n"
               "Monday,11:00,10:00,IT-201,Backwards\n"
               "Monday,12:00,13:00,LAB-999,Unknown room\n"
               "Monday,09:30,10:30,ECE-101,Overlaps row 2\n"
               "Tuesday,09:00,10:00,IT-201,\n")
        response = self.upload(bad)
        self.assertEqual(response.status_code, 400)
        errors = {e["row"]: e["message"] for e in response.json()["errors"]}
        self.assertEqual(sorted(errors), [3, 4, 5, 6, 7])
        self.assertIn('Unknown day "Funday"', errors[3])
        self.assertIn("End must be after start", errors[4])
        self.assertIn('Unknown room "LAB-999"', errors[5])
        self.assertIn("(row 2)", errors[6])
        self.assertIn("Activity is missing", errors[7])
        self.assertEqual(Timetable.objects.count(), 1)   # nothing saved

    def test_missing_columns_and_empty_files(self):
        self.assertIn("Missing column(s): room_id",
                      self.upload("day,start,end,activity\nMonday,09:00,10:00,X\n").json()["detail"])
        self.assertEqual(self.upload("").status_code, 400)
        self.assertEqual(self.upload("day,start,end,room_id,activity\n").status_code, 400)

    def test_alternative_column_names_and_formats(self):
        text = "Weekday,Classroom,Start,End,Subject\nmon,ece-101,2:00 PM,3:00 PM,Labs\n"
        response = self.upload(text)
        self.assertEqual(response.status_code, 201, response.content)
        entry = response.json()["entries"][0]
        self.assertEqual((entry["day"], entry["roomId"], entry["start"], entry["end"]), ("Monday", "ECE-101", "14:00",
                                                                                         "15:00"))


class ActivationTests(ClassroomTestCase):
    def upload_b(self):
        return Timetable.objects.get(pk=self.upload(read("Timetable_B_Updated.csv")).json()["id"])

    def activate(self, timetable):
        return self.api(self.prof).post(f"{TIMETABLES}{timetable.id}/activate/")

    def test_activating_b_changes_availability_and_recommendations(self):
        b = self.upload_b()
        response = self.activate(b)
        self.assertEqual(response.status_code, 200, response.content)
        body = self.find(self.monday, "11:00", group=8)
        self.assertEqual(body["recommended"]["id"], "ECE-102")
        self.assertEqual(body["timetable"]["version"], b.version)
        blocked = {r["id"]: r["reason"] for r in body["unavailable"]}
        self.assertEqual(blocked["ECE-101"], "Timetabled: Microcontrollers 11:00–12:00")
        self.assertIn("AI Workshop", blocked["CSE-301"])
        self.assertEqual(self.book(self.alice, "ECE-101", self.monday, 11).status_code, 409)
        # Monday 15:00 in ECE-102 is free now.
        self.assertEqual(self.book(self.alice, "ECE-102", self.monday, 15).status_code, 201)

    def test_previous_version_is_archived_and_can_be_reactivated(self):
        a = Timetable.objects.get(source_filename="Timetable_A_Initial.csv")
        b = self.upload_b()
        self.activate(b)
        a.refresh_from_db()
        self.assertEqual(a.status, "archived")
        self.assertEqual(self.activate(a).status_code, 200)   # rollback
        self.assertEqual(self.find(self.monday, "11:00", group=8)["recommended"]["id"], "ECE-101")
        self.assertEqual(Timetable.objects.filter(status="active").count(), 1)

    def test_active_timetable_persists_in_the_database(self):
        b = self.upload_b()
        self.activate(b)
        # A fresh read from the database (what a restarted server sees).
        fresh = Timetable.objects.get(status=Timetable.Status.ACTIVE)
        self.assertEqual((fresh.pk, fresh.entries.count()), (b.pk, 19))
        self.assertEqual(self.api(self.alice).get(TIMETABLES + "active/").json()["version"], b.version)

    def test_conflicts_are_detected_with_a_suggested_room(self):
        booking = self.book(self.alice, "ECE-101", self.monday, 11).json()
        b = self.upload_b()
        conflicts = self.api(self.prof).get(f"{TIMETABLES}{b.id}/conflicts/").json()
        self.assertEqual(len(conflicts), 1)
        self.assertEqual((conflicts[0]["bookingId"], conflicts[0]["clashesWith"], conflicts[0]["suggestedRoomId"]),
                         (booking["id"], "Microcontrollers", "ECE-102"))

    def test_activation_is_blocked_and_bookings_are_not_touched(self):
        booking = self.book(self.alice, "ECE-101", self.monday, 11).json()
        b = self.upload_b()
        response = self.activate(b)
        self.assertEqual(response.status_code, 409)
        self.assertIn("1 upcoming booking(s) clash", response.json()["detail"])
        stored = RoomBooking.objects.get(pk=booking["id"])
        self.assertEqual((stored.status, stored.room_id), ("active", "ECE-101"))
        b.refresh_from_db()
        self.assertEqual(b.status, "draft")
        self.assertEqual(Timetable.objects.get(status="active").source_filename, "Timetable_A_Initial.csv")

    def test_faculty_reassign_then_activate(self):
        booking = self.book(self.alice, "ECE-101", self.monday, 11).json()
        b = self.upload_b()
        moved = self.api(self.prof).post(f"{TIMETABLES}{b.id}/resolve/", {"bookingId": booking["id"],
                                                                          "action": "reassign"}, format="json")
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(moved.json()["roomId"], "ECE-102")
        self.assertIn("Moved from ECE-101 to ECE-102 by Priya Nair", moved.json()["note"])
        mine = self.api(self.alice).get(BOOKINGS + "mine/").json()
        self.assertEqual((mine[0]["roomId"], mine[0]["status"]), ("ECE-102", "active"))
        self.assertTrue(TimetableEvent.objects.filter(action="booking_reassigned", booking_id=booking["id"]).exists())
        self.assertEqual(self.activate(b).status_code, 200)

    def test_reassign_to_a_chosen_room_is_checked(self):
        booking = self.book(self.alice, "ECE-101", self.monday, 11).json()
        b = self.upload_b()
        response = self.api(self.prof).post(f"{TIMETABLES}{b.id}/resolve/", {
            "bookingId": booking["id"], "action": "reassign", "roomId": "CSE-301"}, format="json")
        self.assertEqual(response.status_code, 400)   # CSE-301 gets AI Workshop in B
        self.assertIn("AI Workshop", str(response.json()))

    def test_faculty_cancel_then_activate(self):
        booking = self.book(self.alice, "ECE-101", self.monday, 11).json()
        b = self.upload_b()
        response = self.api(self.prof).post(f"{TIMETABLES}{b.id}/resolve/", {"bookingId": booking["id"],
                                                                             "action": "cancel"}, format="json")
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertIn("Microcontrollers", response.json()["note"])
        self.assertTrue(TimetableEvent.objects.filter(action="booking_cancelled").exists())
        self.assertEqual(self.activate(b).status_code, 200)

    def test_students_cannot_resolve_conflicts(self):
        booking = self.book(self.alice, "ECE-101", self.monday, 11).json()
        b = self.upload_b()
        response = self.api(self.alice).post(f"{TIMETABLES}{b.id}/resolve/", {"bookingId": booking["id"],
                                                                              "action": "cancel"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(RoomBooking.objects.get(pk=booking["id"]).status, "active")

    def test_audit_history(self):
        b = self.upload_b()
        self.activate(b)
        actions = [e["action"] for e in self.api(self.prof).get(TIMETABLES + "history/").json()]
        self.assertEqual(actions[:2], ["activated", "uploaded"])
        self.assertIn("seeded", actions)


class ConcurrencyTests(ClassroomTestCase):
    def test_booking_takes_the_write_lock_before_reading_seats(self):
        start = self.at(self.monday, 14)
        with CaptureQueriesContext(connection) as queries:
            services.book_room(self.alice, "IT-201", start, 60, attendees=8, mode="shared")
        sql = [q["sql"].upper() for q in queries]
        first_update = next(i for i, q in enumerate(sql) if q.startswith("UPDATE \"ATTENDANCE_CLASSROOM\""))
        first_seat_read = next(i for i, q in enumerate(sql) if "SPACES_ROOMBOOKING" in q and q.startswith("SELECT"))
        self.assertLess(first_update, first_seat_read)

    def test_back_to_back_bookings_never_exceed_capacity(self):
        accepted = 0
        for user_number in range(10):
            user = get_user_model().objects.create_user(f"s{user_number}", password="unused-test-pw")
            if self.book(user, "IT-201", self.monday, 14, group=7).status_code == 201:
                accepted += 1
        self.assertEqual(accepted, 8)   # 8 × 7 = 56 ≤ 60; a 9th would need 63
        self.assertEqual(self.seats("IT-201", self.monday, "14:00"), 4)
