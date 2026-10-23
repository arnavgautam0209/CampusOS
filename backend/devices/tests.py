from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from attendance.models import AttendanceRecord, AttendanceSession, CampusCard, Classroom

from .models import Device, ScanEvent

URL = "/api/v1/devices/scan/"
UID = "04A1B2C3"


class ScanTestCase(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.student = User.objects.create_user("alice", first_name="Alice", last_name="Rao",
                                                password="unused-test-pw")
        self.faculty = User.objects.create_user("prof", password="unused-test-pw", is_staff=True)
        self.card = CampusCard.objects.create(uid=UID, user=self.student)
        self.device = Device.objects.get(pk="READER-ROOM-101")
        self.key = self.device.issue_key()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Device {self.key}")

    def open_session(self, classroom="ROOM-101", title="CS201 Lecture 5"):
        return AttendanceSession.objects.create(classroom_id=classroom, title=title, opened_by=self.faculty)

    def scan(self, uid=UID, classroom="ROOM-101", client=None):
        return (client or self.client).post(URL, {"uid": uid, "classroomId": classroom}, format="json")


class ContractTests(ScanTestCase):
    def test_marked_201(self):
        session = self.open_session()
        response = self.scan()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["result"], "marked")
        self.assertEqual(body["student"], "Alice Rao")
        self.assertEqual(body["message"], "Attendance marked: Alice Rao")
        self.assertEqual(body["sessionId"], session.id)
        record = AttendanceRecord.objects.get()
        self.assertEqual((record.session, record.student, record.device, record.card),
                         (session, self.student, self.device, self.card))
        self.assertEqual(record.source, "card")

    def test_duplicate_200_creates_nothing_new(self):
        self.open_session()
        first = self.scan().json()
        response = self.scan()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["result"], "duplicate")
        self.assertEqual(body["message"], "Already marked: Alice Rao")
        self.assertEqual(body["markedAt"], first["markedAt"])
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_unknown_card_404(self):
        self.open_session()
        response = self.scan(uid="DEADBEEF")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["result"], "unknown_card")
        self.assertEqual(response.json()["uid"], "DEADBEEF")
        self.assertIn("DEADBEEF", response.json()["message"])
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_deactivated_card_is_unknown(self):
        self.open_session()
        self.card.is_active = False
        self.card.save()
        self.assertEqual(self.scan().json()["result"], "unknown_card")

    def test_no_session_409(self):
        response = self.scan()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["result"], "no_session")
        self.assertIn("ROOM-101", response.json()["message"])

    def test_closed_session_is_no_session(self):
        session = self.open_session()
        session.closed_at = timezone.now()
        session.save()
        self.assertEqual(self.scan().status_code, 409)

    def test_seven_and_ten_byte_uids(self):
        self.open_session()
        for uid in ["04A1B2C3D4E5F6", "04A1B2C3D4E5F6A7B8C9"]:
            other = get_user_model().objects.create_user(f"user-{uid}", password="unused-test-pw")
            CampusCard.objects.create(uid=uid, user=other)
            self.assertEqual(self.scan(uid=uid).status_code, 201)

    def test_uid_formatting_is_forgiving(self):
        self.open_session()
        self.assertEqual(self.scan(uid="04:a1:b2:c3").status_code, 201)
        self.assertEqual(self.scan(uid="04 A1 B2 C3").json()["result"], "duplicate")


class BadRequestTests(ScanTestCase):
    def assert_400(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["message"])

    def test_missing_uid(self):
        self.assert_400(self.client.post(URL, {"classroomId": "ROOM-101"}, format="json"))

    def test_bad_uid_formats(self):
        for uid in ["", "XYZ12345", "04A1B2", "04A1B2C3D4"]:
            self.assert_400(self.scan(uid=uid))

    def test_missing_classroom(self):
        self.assert_400(self.client.post(URL, {"uid": UID}, format="json"))

    def test_not_json(self):
        response = self.client.post(URL, "uid=04A1B2C3", content_type="text/plain")
        self.assert_400(response)
        self.assertIn("Content-Type", response.json()["message"])

    def test_missing_content_type_header_gets_helpful_message(self):
        # What an ESP32 sends if the sketch forgets addHeader("Content-Type", ...).
        response = self.client.post(URL, '{"uid":"04A1B2C3","classroomId":"ROOM-101"}',
                                    content_type="application/x-www-form-urlencoded")
        self.assert_400(response)
        self.assertIn("Content-Type", response.json()["message"])

    def test_malformed_json(self):
        self.assert_400(self.client.post(URL, '{"uid": "04A1B2C3",', content_type="application/json"))

    def test_json_that_is_not_an_object(self):
        self.assert_400(self.client.post(URL, '["04A1B2C3"]', content_type="application/json"))

    def test_reader_registered_to_another_room(self):
        Classroom.objects.create(id="ROOM-102", name="Room 102")
        self.open_session(classroom="ROOM-102")
        response = self.scan(classroom="ROOM-102")
        self.assert_400(response)
        self.assertIn("ROOM-101", response.json()["message"])
        self.assertFalse(AttendanceRecord.objects.exists())
        self.assertEqual(ScanEvent.objects.get().result, "wrong_classroom")

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


class DeviceAuthTests(ScanTestCase):
    def assert_401(self, client):
        response = self.scan(client=client)
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json()["message"])
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_missing_key(self):
        self.open_session()
        self.assert_401(APIClient())

    def test_wrong_key(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Device dev_not-a-real-key")
        self.assert_401(client)

    def test_disabled_device(self):
        self.device.is_active = False
        self.device.save()
        self.assert_401(self.client)

    def test_user_token_cannot_scan(self):
        # A student's app token must never work as a reader key.
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.student).key}")
        self.assert_401(client)

    def test_new_key_replaces_old_and_only_hash_is_stored(self):
        new_key = self.device.issue_key()
        self.device.refresh_from_db()
        self.assertNotIn(new_key, (self.device.key_hash, self.device.key_prefix))
        self.assertTrue(new_key.startswith(self.device.key_prefix))
        self.assert_401(self.client)
        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f"Device {new_key}")
        self.open_session()
        self.assertEqual(self.scan(client=fresh).status_code, 201)

    def test_device_without_key_cannot_authenticate(self):
        Device.objects.create(id="READER-NOKEY", name="No key", classroom_id="ROOM-101")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Device ")
        self.assert_401(client)

    def test_device_key_command_prints_working_key(self):
        out = StringIO()
        call_command("device_key", "READER-ROOM-101", stdout=out)
        key = out.getvalue().strip().splitlines()[-1]
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Device {key}")
        self.open_session()
        self.assertEqual(self.scan(client=client).status_code, 201)


class AuditAndIntegrityTests(ScanTestCase):
    def test_every_scan_is_logged_and_last_seen_updated(self):
        self.scan()                    # no session
        self.open_session()
        self.scan()                    # marked
        self.scan()                    # duplicate
        self.scan(uid="DEADBEEF")      # unknown
        results = list(ScanEvent.objects.order_by("created_at", "id").values_list("result", flat=True))
        self.assertEqual(results, ["no_session", "marked", "duplicate", "unknown_card"])
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen_at)

    def test_new_session_allows_marking_again(self):
        first = self.open_session(title="Lecture 1")
        self.scan()
        first.closed_at = timezone.now()
        first.save()
        self.open_session(title="Lecture 2")
        self.assertEqual(self.scan().json()["result"], "marked")
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_only_one_open_session_per_classroom(self):
        self.open_session()
        with self.assertRaises(IntegrityError):
            self.open_session(title="Another")

    def test_database_blocks_double_attendance(self):
        session = self.open_session()
        AttendanceRecord.objects.create(session=session, student=self.student)
        with self.assertRaises(IntegrityError):
            AttendanceRecord.objects.create(session=session, student=self.student)

    def test_card_uid_is_stored_uppercase(self):
        other = get_user_model().objects.create_user("bob", password="unused-test-pw")
        self.assertEqual(CampusCard.objects.create(uid="0a0b0c0d", user=other).uid, "0A0B0C0D")

    def test_seed_creates_classroom_and_reader_without_key(self):
        Device.objects.all().delete()
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)
        device = Device.objects.get(pk="READER-ROOM-101")
        self.assertEqual(device.classroom_id, "ROOM-101")
        self.assertEqual(device.key_hash, "")
