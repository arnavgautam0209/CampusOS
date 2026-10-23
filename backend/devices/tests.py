from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from attendance.models import AttendanceRecord, AttendanceSession, CampusCard, Classroom
from bookings.models import Booking
from labs.models import Lab
from skillpass.models import UserCertification

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


class LabCheckInTests(TestCase):
    """Lab door readers: {"uid", "labId"} checks a student in to their booking."""

    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.student = User.objects.create_user("alice", first_name="Alice", last_name="Rao",
                                                password="unused-test-pw")
        self.faculty = User.objects.create_user("prof", password="unused-test-pw", is_staff=True)
        CampusCard.objects.create(uid=UID, user=self.student)
        self.device = Device.objects.get(pk="READER-LAB001")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Device {self.device.issue_key()}")
        self.now = timezone.now()

    def book(self, lab="LAB001", starts_in=-5, minutes=60, user=None):
        start = self.now + timedelta(minutes=starts_in)
        return Booking.objects.create(user=user or self.student, lab_id=lab, start=start,
                                      end=start + timedelta(minutes=minutes))

    def tap(self, lab="LAB001", uid=UID, client=None):
        return (client or self.client).post(URL, {"uid": uid, "labId": lab}, format="json")

    def test_granted_records_actual_start(self):
        booking = self.book()
        response = self.tap()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["result"], "granted")
        self.assertEqual(body["student"], "Alice Rao")
        self.assertTrue(body["message"].startswith("Alice Rao: Access granted until"))
        self.assertEqual(body["bookingId"], str(booking.id))
        booking.refresh_from_db()
        self.assertIsNotNone(booking.checked_in_at)
        self.assertEqual(booking.checked_in_device, self.device)
        event = ScanEvent.objects.get()
        self.assertEqual((event.result, event.booking, event.classroom_id_sent), ("granted", booking, "LAB001"))

    def test_repeat_tap_keeps_first_check_in(self):
        booking = self.book()
        first = self.tap().json()["checkedInAt"]
        response = self.tap()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "already_checked_in")
        self.assertEqual(response.json()["checkedInAt"], first)

    def test_check_in_opens_ten_minutes_early(self):
        self.book(starts_in=8)
        self.assertEqual(self.tap().json()["result"], "granted")

    def test_too_early_is_denied_with_opening_time(self):
        booking = self.book(starts_in=60)
        response = self.tap()
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual((body["result"], body["reason"]), ("denied", "too_early"))
        opens = timezone.localtime(booking.start - timedelta(minutes=10))
        self.assertIn(f"{opens:%H:%M}", body["message"])
        booking.refresh_from_db()
        self.assertIsNone(booking.checked_in_at)

    def test_no_booking_is_denied(self):
        response = self.tap()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["reason"], "no_booking")

    def test_bookings_that_dont_count(self):
        other = get_user_model().objects.create_user("bob", password="unused-test-pw")
        self.book(user=other)                                   # someone else's
        self.book(lab="LAB004")                                 # another lab
        self.book(starts_in=-120, minutes=60)                   # already ended
        cancelled = self.book()
        cancelled.status = "cancelled"
        cancelled.save()
        self.assertEqual(self.tap().json()["reason"], "no_booking")

    def test_restricted_lab_needs_certification_through_the_session(self):
        reader = Device.objects.create(id="READER-LAB002", name="Electronics door", lab_id="LAB002")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Device {reader.issue_key()}")
        booking = self.book(lab="LAB002")

        response = self.tap(lab="LAB002", client=client)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["reason"], "certification_required")
        self.assertEqual(response.json()["missingCertifications"], ["CERT-ELEC-BASIC"])

        record = UserCertification.objects.create(user=self.student, certification_id="CERT-ELEC-BASIC",
                                                  status="approved", approved_by=self.faculty,
                                                  expires_at=booking.end - timedelta(minutes=1))
        self.assertEqual(self.tap(lab="LAB002", client=client).json()["reason"], "certification_required")
        record.expires_at = None
        record.save()
        self.assertEqual(self.tap(lab="LAB002", client=client).json()["result"], "granted")

    def test_closed_lab_is_denied(self):
        Lab.objects.filter(pk="LAB001").update(is_open_for_booking=False)
        self.book()
        self.assertEqual(self.tap().json()["reason"], "lab_closed")

    def test_unknown_card(self):
        response = self.tap(uid="DEADBEEF")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["result"], "unknown_card")

    def test_wrong_or_missing_lab_id(self):
        self.book()
        wrong = self.tap(lab="LAB004")
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("LAB001", wrong.json()["message"])
        missing = self.client.post(URL, {"uid": UID, "classroomId": "ROOM-101"}, format="json")
        self.assertEqual(missing.status_code, 400)
        self.assertIn("labId", missing.json()["message"])

    def test_reader_without_location(self):
        reader = Device.objects.create(id="READER-SPARE", name="Spare")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Device {reader.issue_key()}")
        response = client.post(URL, {"uid": UID, "classroomId": "ROOM-101"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("isn't assigned", response.json()["message"])

    def test_reader_cannot_be_in_classroom_and_lab(self):
        with self.assertRaises(IntegrityError):
            Device.objects.create(id="READER-BOTH", name="Both", classroom_id="ROOM-101", lab_id="LAB001")

    def test_checked_in_booking_shows_in_api_and_cannot_be_cancelled(self):
        booking = self.book()
        self.tap()
        app = APIClient()
        app.force_authenticate(self.student)
        listed = app.get("/api/v1/bookings/").json()[0]
        self.assertIsNotNone(listed["checkedInAt"])
        response = app.post(f"/api/v1/bookings/{booking.id}/cancel/")
        self.assertEqual(response.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status, "active")


SIMPLE_URL = "/api/scan/"


class SimpleScanTests(TestCase):
    """POST /api/scan/ {card_uid, classroom}: the AttendX firmware contract."""

    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.student = User.objects.create_user("ECE001", first_name="Asha", last_name="Verma",
                                                password="unused-test-pw")
        CampusCard.objects.create(uid="A1B2C3D4", user=self.student)
        self.client = APIClient()
        self.session = AttendanceSession.objects.create(classroom_id="ECE", title="ECE Lab Lecture 1")

    def scan(self, uid="A1B2C3D4", classroom="ECE", client=None):
        return (client or self.client).post(SIMPLE_URL, {"card_uid": uid, "classroom": classroom}, format="json")


@override_settings(DEBUG=True, CAMPUSOS_OPEN_SCAN=True)
class SimpleScanOpenModeTests(SimpleScanTests):
    def test_present_created(self):
        response = self.scan()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(
            {k: body[k] for k in ["status", "created", "student", "roll_number", "classroom", "message"]},
            {"status": "present", "created": True, "student": "Asha Verma", "roll_number": "ECE001",
             "classroom": "ECE", "message": "Attendance marked successfully"},
        )
        record = AttendanceRecord.objects.get()
        self.assertEqual((record.student, record.session, record.device_id),
                         (self.student, self.session, "READER-ECE"))
        self.assertEqual(ScanEvent.objects.get().device_id, "READER-ECE")

    def test_duplicate_is_200_not_created(self):
        self.scan()
        response = self.scan()
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["status"], response.json()["created"], response.json()["message"]),
                         ("present", False, "Attendance already marked"))
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_unknown_card_is_404_and_creates_nothing(self):
        users_before = get_user_model().objects.count()
        response = self.scan(uid="DEADBEEF")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"status": "unknown_card", "message": "Card is not registered",
                                           "card_uid": "DEADBEEF", "classroom": "ECE"})
        self.assertFalse(AttendanceRecord.objects.exists())
        self.assertEqual(get_user_model().objects.count(), users_before)

    def test_uid_and_classroom_are_normalized(self):
        self.assertEqual(self.scan(uid="a1:b2:c3:d4", classroom="ece").status_code, 201)
        self.assertEqual(self.scan(uid=" a1 b2-c3 d4 ").json()["created"], False)

    def test_no_open_session_is_409(self):
        self.session.closed_at = timezone.now()
        self.session.save()
        response = self.scan()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "no_session")

    def test_validation_errors_are_400_with_field_messages(self):
        cases = [
            ({"classroom": "ECE"}, "card_uid"),
            ({"card_uid": "ZZZ", "classroom": "ECE"}, "card_uid"),
            ({"card_uid": "A1B2C3"}, "classroom"),
            ({"card_uid": "A1B2C3D4", "classroom": "NOPE"}, "classroom"),
        ]
        for payload, field in cases:
            response = self.client.post(SIMPLE_URL, payload, format="json")
            self.assertEqual(response.status_code, 400, payload)
            self.assertEqual(response.json()["status"], "error")
            self.assertIn(field, response.json()["errors"])
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_not_json_is_400(self):
        response = self.client.post(SIMPLE_URL, "card_uid=A1B2C3D4", content_type="text/plain")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Content-Type", response.json()["message"])

    def test_classroom_without_reader_is_400(self):
        Classroom.objects.create(id="MECH", name="Mechanical")
        AttendanceSession.objects.create(classroom_id="MECH", title="x")
        response = self.scan(classroom="MECH")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No reader", response.json()["message"])

    def test_wrong_device_key_is_still_401(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Device dev_wrong")
        response = self.scan(client=client)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "unauthorized")

    def test_get_is_405_json(self):
        response = self.client.get(SIMPLE_URL)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["status"], "error")


class SimpleScanSecuredTests(SimpleScanTests):
    def test_without_key_is_401_by_default(self):
        response = self.scan()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "unauthorized")
        self.assertIn("Authorization: Device", response.json()["message"])
        self.assertFalse(AttendanceRecord.objects.exists())

    @override_settings(DEBUG=False, CAMPUSOS_OPEN_SCAN=True)
    def test_open_mode_is_ignored_when_debug_is_off(self):
        self.assertEqual(self.scan().status_code, 401)

    def test_device_key_works_without_open_mode(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Device {Device.objects.get(pk='READER-ECE').issue_key()}")
        self.assertEqual(self.scan(client=client).status_code, 201)

    def test_key_for_another_classroom_is_400(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Device {Device.objects.get(pk='READER-ROOM-101').issue_key()}")
        response = self.scan(client=client)
        self.assertEqual(response.status_code, 400)
        self.assertIn("ROOM-101", response.json()["message"])

    def test_v1_endpoint_unchanged(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Device {Device.objects.get(pk='READER-ECE').issue_key()}")
        response = client.post(URL, {"uid": "A1B2C3D4", "classroomId": "ECE"}, format="json")
        self.assertEqual((response.status_code, response.json()["result"]), (201, "marked"))
