from io import StringIO

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase
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

    def reader_info(self, reader_id):
        return next(r for r in self.staff.get(LIVE).json()["readers"] if r["id"] == reader_id)

    def test_readers_show_key_and_last_seen(self):
        room = self.reader_info("READER-ROOM-101")
        self.assertTrue(room["hasKey"])
        self.assertIsNone(room["lastSeenAt"])
        self.assertEqual((room["classroomId"], room["labId"]), ("ROOM-101", None))
        self.tap("04A1B2C3")
        self.assertIsNotNone(self.reader_info("READER-ROOM-101")["lastSeenAt"])

    def test_lab_readers_show_their_lab(self):
        lab = self.reader_info("READER-LAB001")
        self.assertEqual((lab["classroomId"], lab["labId"]), (None, "LAB001"))

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


class SessionControlTests(AttendanceViewTestCase):
    OPEN = "/api/v1/attendance/sessions/"

    def close_url(self, session_id):
        return f"/api/v1/attendance/sessions/{session_id}/close/"

    def test_faculty_opens_session_and_reader_starts_marking(self):
        self.assertEqual(self.tap("04A1B2C3").status_code, 409)
        response = self.staff.post(self.OPEN, {"classroomId": "ROOM-101", "title": " CS201 Lecture 6 "},
                                   format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["title"], "CS201 Lecture 6")
        self.assertEqual(body["openedBy"], "Priya Nair")
        self.assertIsNone(body["closedAt"])
        self.assertEqual(AttendanceSession.objects.get(pk=body["id"]).opened_by, self.prof)
        self.assertEqual(self.tap("04A1B2C3").status_code, 201)

    def test_opening_twice_in_one_room_is_409(self):
        self.open_session(title="Lecture 5")
        response = self.staff.post(self.OPEN, {"classroomId": "ROOM-101", "title": "Lecture 6"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("Lecture 5", response.json()["detail"])
        self.assertEqual(AttendanceSession.objects.count(), 1)

    def test_open_validation(self):
        bad = [
            ({"classroomId": "ROOM-101", "title": "  "}, "title"),
            ({"classroomId": "ROOM-101"}, "title"),
            ({"classroomId": "ROOM-101", "title": "x" * 121}, "title"),
            ({"classroomId": "NOPE", "title": "Lecture"}, "classroomId"),
        ]
        for payload, field in bad:
            response = self.staff.post(self.OPEN, payload, format="json")
            self.assertEqual(response.status_code, 400, payload)
            self.assertIn(field, response.json())
        self.assertFalse(AttendanceSession.objects.exists())

    def test_faculty_closes_session_and_reader_stops(self):
        session = self.open_session()
        self.tap("04A1B2C3")
        response = self.staff.post(self.close_url(session.id))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["closedAt"])
        self.assertEqual(len(response.json()["records"]), 1)
        session.refresh_from_db()
        self.assertEqual(session.closed_by, self.prof)
        self.assertEqual(self.tap("0B0B0B0B").json()["result"], "no_session")
        self.assertEqual(self.staff.get(LIVE).json()["openSessions"], [])

    def test_closing_twice_is_400_and_unknown_is_404(self):
        session = self.open_session()
        self.staff.post(self.close_url(session.id))
        self.assertEqual(self.staff.post(self.close_url(session.id)).status_code, 400)
        self.assertEqual(self.staff.post(self.close_url(9999)).status_code, 404)

    def test_room_can_reopen_after_close(self):
        session = self.open_session()
        self.staff.post(self.close_url(session.id))
        response = self.staff.post(self.OPEN, {"classroomId": "ROOM-101", "title": "Next"}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_students_and_anonymous_cannot_open_or_close(self):
        session = self.open_session()
        payload = {"classroomId": "ROOM-101", "title": "Sneaky"}
        self.assertEqual(self.student.post(self.OPEN, payload, format="json").status_code, 403)
        self.assertEqual(APIClient().post(self.OPEN, payload, format="json").status_code, 401)
        self.assertEqual(self.student.post(self.close_url(session.id)).status_code, 403)
        session.refresh_from_db()
        self.assertIsNone(session.closed_at)

    def test_live_lists_classrooms_with_open_state(self):
        Classroom.objects.create(id="ROOM-102", name="Room 102")
        self.open_session()
        rooms = {room["id"]: room for room in self.staff.get(LIVE).json()["classrooms"]}
        self.assertTrue(rooms["ROOM-101"]["hasOpenSession"])
        self.assertFalse(rooms["ROOM-102"]["hasOpenSession"])
        self.assertEqual(rooms["ROOM-102"]["name"], "Room 102")

    def test_admin_close_action_records_who_closed(self):
        session = self.open_session()
        request = RequestFactory().post("/admin/")
        request.user = self.prof
        request.session = {}
        request._messages = FallbackStorage(request)
        site._registry[AttendanceSession].close_sessions(request, AttendanceSession.objects.all())
        session.refresh_from_db()
        self.assertEqual(session.closed_by, self.prof)
        self.assertIsNotNone(session.closed_at)


class HardwareCommandTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)

    def run_command(self, *args):
        out = StringIO()
        call_command(*args, stdout=out)
        return out.getvalue()

    def test_register_student_creates_user_and_card(self):
        self.run_command("register_student", "ECE001", "a1:b2:c3:d4", "--name", "Asha Verma")
        student = get_user_model().objects.get(username="ECE001")
        self.assertEqual(student.get_full_name(), "Asha Verma")
        self.assertFalse(student.has_usable_password())
        self.assertEqual(CampusCard.objects.get(uid="A1B2C3D4").user, student)
        # Running it again is safe.
        self.run_command("register_student", "ECE001", "A1B2C3D4")
        self.assertEqual(CampusCard.objects.count(), 1)

    def test_register_student_refuses_someone_elses_card(self):
        self.run_command("register_student", "ECE001", "A1B2C3D4")
        with self.assertRaises(CommandError):
            self.run_command("register_student", "ECE002", "A1B2C3D4")
        with self.assertRaises(CommandError):
            self.run_command("register_student", "ECE003", "not-hex")

    def test_open_and_close_session(self):
        self.assertIn("Opened", self.run_command("open_session", "ECE", "Test lecture"))
        self.assertTrue(AttendanceSession.objects.filter(classroom_id="ECE", closed_at__isnull=True).exists())
        with self.assertRaises(CommandError):
            self.run_command("open_session", "ECE")
        self.assertIn("Closed", self.run_command("open_session", "ECE", "--close"))
        with self.assertRaises(CommandError):
            self.run_command("open_session", "ECE", "--close")
        with self.assertRaises(CommandError):
            self.run_command("open_session", "NOPE")
