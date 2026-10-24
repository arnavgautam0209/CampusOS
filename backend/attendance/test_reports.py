import csv
import io
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from devices.models import Device

from .models import AttendanceRecord, AttendanceSession, CampusCard, ClassroomEnrollment
from .reports import build_report

SIMPLE_SCAN = "/api/scan/"
SESSIONS = "/api/v1/attendance/sessions/"
ROSTER = [
    ("ECE001", "Aarav", "Sharma", "A1B2C3D4"),
    ("ECE002", "Riya", "Verma", "B1C2D3E4"),
    ("ECE003", "Kabir", "Mehta", "C1D2E3F4"),
    ("ECE004", "Ananya", "Singh", "D1E2F3A4"),
]


def report_url(session, suffix=""):
    return f"{SESSIONS}{session.id}/report/{suffix}"


def pdf_text(response):
    reader = PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() for page in reader.pages)


class ReportTestCase(TestCase):
    """Four students enrolled in ECE, each with a card; scans go through the real /api/scan/ endpoint."""

    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.prof = User.objects.create_user("prof", first_name="Demo", last_name="Faculty",
                                             password="unused-test-pw", is_staff=True)
        self.students = {}
        enrolled_at = timezone.now() - timedelta(days=7)
        for roll, first, last, uid in ROSTER:
            # Usernames deliberately differ from roll numbers: reports must use the roster's roll number.
            student = User.objects.create_user(f"user-{roll.lower()}", first_name=first, last_name=last,
                                               password="unused-test-pw")
            CampusCard.objects.create(uid=uid, user=student)
            ClassroomEnrollment.objects.create(classroom_id="ECE", student=student, roll_number=roll,
                                               enrolled_at=enrolled_at)
            self.students[roll] = student
        self.reader = APIClient()
        self.reader.credentials(HTTP_AUTHORIZATION=f"Device {Device.objects.get(pk='READER-ECE').issue_key()}")
        self.staff = APIClient()
        self.staff.force_authenticate(self.prof)

    def open_session(self, title="Embedded Systems Lecture 01"):
        response = self.staff.post(SESSIONS, {"classroomId": "ECE", "title": title}, format="json")
        self.assertEqual(response.status_code, 201)
        return AttendanceSession.objects.get(pk=response.json()["id"])

    def close(self, session):
        self.assertEqual(self.staff.post(f"{SESSIONS}{session.id}/close/").status_code, 200)

    def tap(self, uid):
        return self.reader.post(SIMPLE_SCAN, {"card_uid": uid, "classroom": "ECE"}, format="json")

    def report(self, session):
        response = self.staff.get(report_url(session))
        self.assertEqual(response.status_code, 200)
        return response.json()

    @staticmethod
    def rolls(entries):
        return [entry["rollNumber"] for entry in entries]


class CountTests(ReportTestCase):
    def test_no_scans_means_nobody_is_present(self):
        session = self.open_session()
        self.close(session)
        body = self.report(session)
        self.assertEqual(body["summary"], {"totalStudents": 4, "present": 0, "absent": 4,
                                           "attendancePercentage": 0.0})
        self.assertEqual(body["presentStudents"], [])
        self.assertEqual(self.rolls(body["absentStudents"]), ["ECE001", "ECE002", "ECE003", "ECE004"])

    def test_one_scan_one_present(self):
        session = self.open_session()
        self.tap("C1D2E3F4")
        self.close(session)
        body = self.report(session)
        self.assertEqual(self.rolls(body["presentStudents"]), ["ECE003"])
        self.assertEqual(body["summary"]["present"], 1)
        self.assertEqual(body["summary"]["attendancePercentage"], 25.0)

    def test_two_scans_two_present_two_absent(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        self.tap("B1C2D3E4")
        self.close(session)
        body = self.report(session)
        self.assertEqual(body["summary"], {"totalStudents": 4, "present": 2, "absent": 2,
                                           "attendancePercentage": 50.0})
        self.assertEqual([s["name"] for s in body["presentStudents"]], ["Aarav Sharma", "Riya Verma"])
        self.assertEqual([s["name"] for s in body["absentStudents"]], ["Kabir Mehta", "Ananya Singh"])
        self.assertEqual({s["status"] for s in body["presentStudents"]}, {"present"})
        self.assertEqual({s["status"] for s in body["absentStudents"]}, {"absent"})
        # Absent students carry no scan data at all.
        for absent in body["absentStudents"]:
            self.assertNotIn("markedAt", absent)
            self.assertNotIn("cardUid", absent)

    def test_percentage_rounds_to_one_decimal(self):
        session = self.open_session()
        for uid in ("A1B2C3D4", "B1C2D3E4", "C1D2E3F4"):
            self.tap(uid)
        ClassroomEnrollment.objects.create(
            classroom_id="ECE", roll_number="ECE005", enrolled_at=timezone.now() - timedelta(days=1),
            student=get_user_model().objects.create_user("user-ece005", password="unused-test-pw"))
        ClassroomEnrollment.objects.create(
            classroom_id="ECE", roll_number="ECE006", enrolled_at=timezone.now() - timedelta(days=1),
            student=get_user_model().objects.create_user("user-ece006", password="unused-test-pw"))
        self.close(session)
        self.assertEqual(self.report(session)["summary"]["attendancePercentage"], 50.0)   # 3 / 6
        ClassroomEnrollment.objects.filter(roll_number="ECE006").delete()
        self.assertEqual(self.report(session)["summary"]["attendancePercentage"], 60.0)   # 3 / 5

    def test_thirds_round(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        ClassroomEnrollment.objects.filter(roll_number="ECE004").delete()
        self.close(session)
        self.assertEqual(self.report(session)["summary"]["attendancePercentage"], 33.3)   # 1 / 3

    def test_empty_classroom_has_no_percentage(self):
        ClassroomEnrollment.objects.all().delete()
        session = self.open_session()
        self.close(session)
        body = self.report(session)
        self.assertEqual(body["summary"], {"totalStudents": 0, "present": 0, "absent": 0,
                                           "attendancePercentage": None})
        self.assertIn("No students are enrolled", pdf_text(self.staff.get(report_url(session, "pdf/"))))


class IntegrityTests(ReportTestCase):
    def test_duplicate_taps_make_one_present_record(self):
        session = self.open_session()
        first = self.tap("A1B2C3D4")
        again = self.tap("A1B2C3D4")
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.close(session)
        body = self.report(session)
        self.assertEqual(self.rolls(body["presentStudents"]), ["ECE001"])
        self.assertEqual(AttendanceRecord.objects.filter(session=session).count(), 1)

    def test_unregistered_card_adds_nobody(self):
        session = self.open_session()
        self.assertEqual(self.tap("DEADBEEF").status_code, 404)
        self.close(session)
        body = self.report(session)
        self.assertEqual(body["summary"]["present"], 0)
        self.assertEqual(body["notEnrolledAttendees"], [])

    def test_scans_after_closing_do_not_change_the_report(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        self.close(session)
        before = self.report(session)
        self.assertEqual(self.tap("B1C2D3E4").status_code, 409)   # no_session
        after = self.report(session)
        self.assertEqual(before["summary"], after["summary"])
        self.assertEqual(before["presentStudents"], after["presentStudents"])
        self.assertEqual(before["session"]["status"], "final")

    def test_new_session_starts_with_nobody_present(self):
        first = self.open_session("Embedded Systems Lecture 01")
        self.tap("A1B2C3D4")
        self.tap("B1C2D3E4")
        self.close(first)
        second = self.open_session("Embedded Systems Lecture 02")
        self.assertEqual(self.report(second)["summary"]["present"], 0)
        self.tap("C1D2E3F4")
        self.assertEqual(self.rolls(self.report(second)["presentStudents"]), ["ECE003"])
        self.assertEqual(self.rolls(self.report(first)["presentStudents"]), ["ECE001", "ECE002"])

    def test_open_session_report_is_provisional(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        body = self.report(session)
        self.assertEqual(body["session"]["status"], "provisional")
        self.assertIsNone(body["session"]["closedAt"])
        self.assertIn("PROVISIONAL", pdf_text(self.staff.get(report_url(session, "pdf/"))))

    def test_roll_numbers_and_timestamps_come_from_records(self):
        session = self.open_session()
        self.tap("B1C2D3E4")
        self.close(session)
        record = AttendanceRecord.objects.get(session=session)
        riya = self.report(session)["presentStudents"][0]
        self.assertEqual(riya["rollNumber"], "ECE002")
        self.assertEqual(riya["username"], "user-ece002")
        self.assertEqual(riya["markedAt"], record.marked_at.isoformat())
        self.assertEqual((riya["source"], riya["cardUid"]), ("card", "B1C2D3E4"))
        self.assertTrue(riya["markedAt"].endswith("+00:00"))   # timezone-aware

    def test_faculty_added_record_is_present_but_not_shown_as_a_scan(self):
        session = self.open_session()
        AttendanceRecord.objects.create(session=session, student=self.students["ECE004"],
                                        source=AttendanceRecord.Source.MANUAL)
        self.close(session)
        ananya = self.report(session)["presentStudents"][0]
        self.assertEqual((ananya["rollNumber"], ananya["source"], ananya["cardUid"]), ("ECE004", "manual", None))
        self.assertIn("Added by faculty", pdf_text(self.staff.get(report_url(session, "pdf/"))))

    def test_attendee_without_enrollment_is_listed_apart_and_not_counted(self):
        outsider = get_user_model().objects.create_user("visitor", first_name="Vik", password="unused-test-pw")
        CampusCard.objects.create(uid="E73D0307", user=outsider)
        session = self.open_session()
        self.tap("E73D0307")
        self.close(session)
        body = self.report(session)
        self.assertEqual(body["summary"]["present"], 0)
        self.assertEqual(body["summary"]["totalStudents"], 4)
        self.assertEqual([a["username"] for a in body["notEnrolledAttendees"]], ["visitor"])

    def test_scan_reply_uses_roster_roll_number(self):
        self.open_session()
        self.assertEqual(self.tap("A1B2C3D4").json()["roll_number"], "ECE001")

    def test_report_queries_do_not_grow_with_class_size(self):
        session = self.open_session()
        for uid in ("A1B2C3D4", "B1C2D3E4"):
            self.tap(uid)
        self.close(session)
        session = AttendanceSession.objects.select_related("classroom", "opened_by").get(pk=session.pk)
        with CaptureQueriesContext(connection) as queries:
            build_report(session)
        self.assertEqual(len(queries), 2)   # roster + records


class RosterPolicyTests(ReportTestCase):
    """Roster = enrolled at any point while the session ran; closed sessions keep theirs."""

    def test_enrolling_after_close_does_not_change_a_closed_report(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        self.close(session)
        newcomer = get_user_model().objects.create_user("user-ece005", password="unused-test-pw")
        ClassroomEnrollment.objects.create(classroom_id="ECE", student=newcomer, roll_number="ECE005")
        self.assertEqual(self.report(session)["summary"]["totalStudents"], 4)

    def test_leaving_after_close_keeps_the_student_on_that_report(self):
        session = self.open_session()
        self.close(session)
        ClassroomEnrollment.objects.filter(roll_number="ECE004").update(left_at=timezone.now())
        self.assertIn("ECE004", self.rolls(self.report(session)["absentStudents"]))
        later = self.open_session("Lecture 02")
        self.assertNotIn("ECE004", self.rolls(self.report(later)["absentStudents"]))
        self.assertEqual(self.report(later)["summary"]["totalStudents"], 3)

    def test_enrolling_during_an_open_session_adds_them(self):
        session = self.open_session()
        newcomer = get_user_model().objects.create_user("user-ece005", password="unused-test-pw")
        ClassroomEnrollment.objects.create(classroom_id="ECE", student=newcomer, roll_number="ECE005")
        self.assertIn("ECE005", self.rolls(self.report(session)["absentStudents"]))

    def test_left_before_session_opened_is_not_on_roster(self):
        ClassroomEnrollment.objects.filter(roll_number="ECE003").update(left_at=timezone.now() - timedelta(hours=1))
        session = self.open_session()
        self.close(session)
        self.assertEqual(self.report(session)["summary"]["totalStudents"], 3)


class AccessTests(ReportTestCase):
    def test_reports_are_faculty_only(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        student = APIClient()
        student.force_authenticate(self.students["ECE001"])
        for suffix in ("", "pdf/", "csv/"):
            self.assertEqual(APIClient().get(report_url(session, suffix)).status_code, 401)
            self.assertEqual(student.get(report_url(session, suffix)).status_code, 403)
            # A reader's device key isn't a user login either.
            self.assertIn(self.reader.get(report_url(session, suffix)).status_code, (401, 403))
        self.assertEqual(student.get(SESSIONS).status_code, 403)

    def test_open_scan_mode_does_not_open_reports(self):
        session = self.open_session()
        with self.settings(DEBUG=True, CAMPUSOS_OPEN_SCAN=True):
            self.assertEqual(APIClient().get(report_url(session)).status_code, 401)
            self.assertEqual(APIClient().get(report_url(session, "pdf/")).status_code, 401)

    def test_missing_session_is_404(self):
        for suffix in ("", "pdf/", "csv/"):
            self.assertEqual(self.staff.get(f"{SESSIONS}99999/report/{suffix}").status_code, 404)

    def test_reports_never_write_attendance(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        with mock.patch.object(AttendanceRecord, "save", side_effect=AssertionError("report wrote a record")):
            for suffix in ("", "pdf/", "csv/"):
                self.assertEqual(self.staff.get(report_url(session, suffix)).status_code, 200)
        self.assertEqual(self.staff.post(report_url(session)).status_code, 405)


class DownloadTests(ReportTestCase):
    def two_present_session(self):
        session = self.open_session()
        self.tap("A1B2C3D4")
        self.tap("B1C2D3E4")
        self.close(session)
        return session

    def test_pdf_is_a_valid_a4_attachment(self):
        session = self.two_present_session()
        response = self.staff.get(report_url(session, "pdf/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Content-Disposition"],
                         f'attachment; filename="AttendX_ECE_Session_{session.id:02d}.pdf"')
        self.assertTrue(response.content.startswith(b"%PDF-"))
        page = PdfReader(io.BytesIO(response.content)).pages[0]
        self.assertEqual((round(float(page.mediabox.width)), round(float(page.mediabox.height))), (595, 842))

    def test_pdf_lists_exactly_the_present_students(self):
        session = self.two_present_session()
        text = pdf_text(self.staff.get(report_url(session, "pdf/")))
        for expected in ("CAMPUSOS — ATTENDX", "Session Attendance Report", "Embedded Systems Lecture 01",
                         "Demo Faculty", "Present Students (2)", "Absent Students (2)", "50%",
                         "Generated by CampusOS AttendX"):
            self.assertIn(expected, text)
        present, absent = text.split("Present Students (2)")[1].split("Absent Students (2)")
        self.assertIn("Aarav Sharma", present)
        self.assertIn("Riya Verma", present)
        self.assertNotIn("Kabir Mehta", present)
        self.assertNotIn("Ananya Singh", present)
        self.assertIn("Kabir Mehta", absent)
        self.assertIn("Ananya Singh", absent)
        self.assertNotIn("PRESENT", absent)
        self.assertEqual(present.count("PRESENT"), 2)

    def test_names_with_markup_characters_are_escaped(self):
        self.students["ECE003"].first_name = "Kabir <&>"
        self.students["ECE003"].save()
        session = self.two_present_session()
        self.assertIn("Kabir <&>", pdf_text(self.staff.get(report_url(session, "pdf/"))))

    def test_csv_export(self):
        session = self.two_present_session()
        response = self.staff.get(report_url(session, "csv/"))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual([(r["Roll Number"], r["Status"]) for r in rows],
                         [("ECE001", "PRESENT"), ("ECE002", "PRESENT"), ("ECE003", "ABSENT"), ("ECE004", "ABSENT")])
        self.assertEqual(rows[2]["Marked At"], "")

    def test_session_list_includes_closed_sessions_with_counts(self):
        session = self.two_present_session()
        rows = self.staff.get(SESSIONS, {"classroom": "ece"}).json()
        self.assertEqual([(r["id"], r["presentCount"]) for r in rows], [(session.id, 2)])
        self.assertIsNotNone(rows[0]["closedAt"])

    def test_session_list_is_newest_first(self):
        older = self.two_present_session()
        AttendanceSession.objects.filter(pk=older.pk).update(opened_at=timezone.now() - timedelta(days=2))
        newer = self.open_session("Lecture 02")
        self.assertEqual([r["id"] for r in self.staff.get(SESSIONS).json()], [newer.id, older.id])


class SeedTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)

    def seed(self):
        call_command("seed_attendance_demo", stdout=StringIO())

    def test_seed_builds_the_two_of_four_demo_and_is_idempotent(self):
        self.seed()
        self.seed()
        User = get_user_model()
        self.assertEqual(User.objects.filter(username__startswith="ECE00").count(), 4)
        self.assertEqual(ClassroomEnrollment.objects.filter(classroom_id="ECE").count(), 4)
        sessions = AttendanceSession.objects.filter(title="Embedded Systems Lecture 01")
        self.assertEqual(sessions.count(), 1)
        session = sessions.get()
        self.assertIsNotNone(session.closed_at)
        report = build_report(session)
        self.assertEqual([s.name for s in report.present], ["Aarav Sharma", "Riya Verma"])
        self.assertEqual([s.roll_number for s in report.absent], ["ECE003", "ECE004"])
        self.assertEqual(report.percentage, 50.0)
        self.assertFalse(User.objects.get(username="ECE001").has_usable_password())
        self.assertTrue(all(session.opened_at < s.marked_at < session.closed_at for s in report.present))

    def test_seed_leaves_an_open_hardware_session_alone(self):
        hardware = AttendanceSession.objects.create(classroom_id="ECE", title="ECE Hardware Test")
        self.seed()
        hardware.refresh_from_db()
        self.assertIsNone(hardware.closed_at)

    def test_seed_refuses_to_overwrite_a_real_student(self):
        get_user_model().objects.create_user("ECE002", first_name="Real", last_name="Person",
                                             password="unused-test-pw")
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(get_user_model().objects.get(username="ECE002").first_name, "Real")
        self.assertFalse(AttendanceSession.objects.filter(title="Embedded Systems Lecture 01").exists())

    def test_seed_refuses_a_card_owned_by_someone_else(self):
        other = get_user_model().objects.create_user("someone", password="unused-test-pw")
        CampusCard.objects.create(uid="A1B2C3D4", user=other)
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(CampusCard.objects.get(uid="A1B2C3D4").user, other)

    def test_register_student_can_enroll_a_real_card(self):
        self.seed()
        call_command("register_student", "ECE003", "e7:3d:03:07", "--classroom", "ECE", stdout=StringIO())
        kabir = get_user_model().objects.get(username="ECE003")
        self.assertEqual(set(kabir.campus_cards.values_list("uid", flat=True)), {"C1D2E3F4", "E73D0307"})
        self.assertEqual(ClassroomEnrollment.objects.filter(student=kabir).count(), 1)
        call_command("register_student", "ECE003", "E73D0307", "--classroom", "ECE", stdout=StringIO())
        self.assertEqual(ClassroomEnrollment.objects.filter(student=kabir).count(), 1)   # still one

    def test_register_student_rejects_unknown_classroom(self):
        with self.assertRaises(CommandError):
            call_command("register_student", "ECE009", "0A0B0C0D", "--classroom", "NOPE", stdout=StringIO())
