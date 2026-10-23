from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from devices.models import Device

from .models import AttendanceRecord, AttendanceSession, CampusCard, Classroom

LIVE = "/api/v1/attendance/live/"
MINE = "/api/v1/attendance/mine/"


class AttendanceViewTestCase(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.alice = User.objects.create_user("alice", first_name="Alice", last_name="Rao",
                                              password="unused-test-pw")
        self.bob = User.objects.create_user("bob", password="unused-test-pw")
        self.prof = User.objects.create_user("prof", first_name="Priya", last_name="Nair",
                                             password="unused-test-pw", is_staff=True)
        CampusCard.objects.create(uid="04A1B2C3", user=self.alice)
        CampusCard.objects.create(uid="0B0B0B0B", user=self.bob)
        self.reader = APIClient()
        self.reader.credentials(HTTP_AUTHORIZATION=f"Device {Device.objects.get(pk='READER-ROOM-101').issue_key()}")
        self.staff = APIClient()
        self.staff.force_authenticate(self.prof)
        self.student = APIClient()
        self.student.force_authenticate(self.alice)

    def open_session(self, title="CS201 Lecture 5", classroom="ROOM-101"):
        return AttendanceSession.objects.create(classroom_id=classroom, title=title, opened_by=self.prof)

    def tap(self, uid):
        return self.reader.post("/api/v1/devices/scan/", {"uid": uid, "classroomId": "ROOM-101"}, format="json")


class LiveTests(AttendanceViewTestCase):
    def test_live_is_staff_only(self):
        self.assertEqual(APIClient().get(LIVE).status_code, 401)
        self.assertEqual(self.student.get(LIVE).status_code, 403)
        self.assertEqual(self.staff.get(LIVE).status_code, 200)

    def test_live_shows_open_session_with_present_students_in_tap_order(self):
        session = self.open_session()
        self.tap("0B0B0B0B")
        self.tap("04A1B2C3")
        body = self.staff.get(LIVE).json()

        self.assertEqual(len(body["openSessions"]), 1)
        live_session = body["openSessions"][0]
        self.assertEqual(live_session["id"], session.id)
        self.assertEqual(live_session["classroomId"], "ROOM-101")
        self.assertEqual(live_session["classroomName"], "Lecture Room 101, Block A")
        self.assertEqual(live_session["openedBy"], "Priya Nair")
        self.assertEqual([r["student"] for r in live_session["records"]], ["bob", "Alice Rao"])
        self.assertEqual(live_session["records"][1]["deviceId"], "READER-ROOM-101")
        self.assertEqual(live_session["records"][1]["source"], "card")
        self.assertTrue(body["generatedAt"])

    def test_closed_sessions_are_not_live(self):
        session = self.open_session()
        session.closed_at = timezone.now()
        session.save()
        self.assertEqual(self.staff.get(LIVE).json()["openSessions"], [])

    def test_recent_scans_newest_first_including_failures(self):
        self.tap("04A1B2C3")          # no session
        self.open_session()
        self.tap("04A1B2C3")          # marked
        self.tap("DEADBEEF")          # unknown
        scans = self.staff.get(LIVE).json()["recentScans"]

        self.assertEqual([s["result"] for s in scans], ["unknown_card", "marked", "no_session"])
        self.assertEqual(scans[0]["uid"], "DEADBEEF")
        self.assertIsNone(scans[0]["student"])
        self.assertEqual(scans[1]["student"], "Alice Rao")
        self.assertEqual(scans[1]["deviceId"], "READER-ROOM-101")
        self.assertEqual(scans[1]["classroomId"], "ROOM-101")

    def test_recent_scans_are_limited(self):
        self.open_session()
        for _ in range(30):
            self.tap("04A1B2C3")
        self.assertEqual(len(self.staff.get(LIVE).json()["recentScans"]), 25)

    def test_readers_show_key_and_last_seen(self):
        readers = self.staff.get(LIVE).json()["readers"]
        self.assertEqual(readers[0]["id"], "READER-ROOM-101")
        self.assertTrue(readers[0]["hasKey"])
        self.assertIsNone(readers[0]["lastSeenAt"])
        self.tap("04A1B2C3")
        self.assertIsNotNone(self.staff.get(LIVE).json()["readers"][0]["lastSeenAt"])

    def test_manual_records_appear_with_source(self):
        session = self.open_session()
        AttendanceRecord.objects.create(session=session, student=self.bob, source="manual")
        record = self.staff.get(LIVE).json()["openSessions"][0]["records"][0]
        self.assertEqual(record["source"], "manual")
        self.assertIsNone(record["deviceId"])

    def test_sessions_in_several_rooms(self):
        Classroom.objects.create(id="ROOM-102", name="Room 102")
        self.open_session(title="A")
        self.open_session(title="B", classroom="ROOM-102")
        rooms = [s["classroomId"] for s in self.staff.get(LIVE).json()["openSessions"]]
        self.assertEqual(rooms, ["ROOM-101", "ROOM-102"])


class MineTests(AttendanceViewTestCase):
    def test_mine_requires_sign_in(self):
        self.assertEqual(APIClient().get(MINE).status_code, 401)

    def test_mine_shows_only_own_records_newest_first(self):
        first = self.open_session(title="Lecture 1")
        self.tap("04A1B2C3")
        self.tap("0B0B0B0B")
        first.closed_at = timezone.now()
        first.save()
        self.open_session(title="Lecture 2")
        self.tap("04A1B2C3")

        records = self.student.get(MINE).json()
        self.assertEqual([r["session"] for r in records], ["Lecture 2", "Lecture 1"])
        self.assertEqual(records[0]["classroomId"], "ROOM-101")
        self.assertEqual(records[0]["classroomName"], "Lecture Room 101, Block A")
        self.assertEqual(records[0]["source"], "card")

    def test_mine_is_empty_for_new_student(self):
        self.assertEqual(self.student.get(MINE).json(), [])
