from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Booking
from labs.models import Lab

from . import services
from .models import Certification, UserCertification

BOOKINGS = "/api/v1/bookings/"
RESTRICTED_LAB = "LAB002"  # Electronics Lab requires CERT-ELEC-BASIC in seed_demo
OPEN_LAB = "LAB001"


class SkillPassTestCase(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.student = User.objects.create_user("student", password="unused-test-pw")
        self.faculty = User.objects.create_user("faculty", password="unused-test-pw", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.faculty_client = APIClient()
        self.faculty_client.force_authenticate(self.faculty)
        self.elec = Certification.objects.get(pk="CERT-ELEC-BASIC")
        self.start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)

    def book(self, lab=RESTRICTED_LAB, minutes=60, start=None):
        return self.client.post(
            BOOKINGS,
            {"labID": lab, "start": (start or self.start).isoformat(), "durationMinutes": minutes},
            format="json",
        )

    def grant(self, cert=None, status=UserCertification.Status.APPROVED, expires_at=None, user=None):
        return UserCertification.objects.create(
            user=user or self.student, certification=cert or self.elec, status=status,
            approved_by=self.faculty if status == UserCertification.Status.APPROVED else None,
            approved_at=timezone.now() if status == UserCertification.Status.APPROVED else None,
            expires_at=expires_at,
        )


class BookingEnforcementTests(SkillPassTestCase):
    def test_restricted_lab_refused_without_certification(self):
        response = self.book()
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["missingCertifications"], ["CERT-ELEC-BASIC"])
        self.assertIn("Basic Electronics Safety", body["detail"])
        self.assertFalse(Booking.objects.exists())

    def test_unrestricted_lab_needs_no_certification(self):
        self.assertEqual(self.book(lab=OPEN_LAB).status_code, 201)

    def test_approved_certification_allows_booking(self):
        self.grant()
        self.assertEqual(self.book().status_code, 201)

    def test_pending_certification_is_not_enough(self):
        self.grant(status=UserCertification.Status.PENDING)
        self.assertEqual(self.book().status_code, 403)

    def test_revoked_certification_is_refused(self):
        self.grant(status=UserCertification.Status.REVOKED)
        self.assertEqual(self.book().status_code, 403)

    def test_expired_certification_is_refused(self):
        self.grant(expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.book().status_code, 403)

    def test_certification_must_last_until_session_ends(self):
        # Expires 30 minutes into a 60-minute session.
        self.grant(expires_at=self.start + timedelta(minutes=30))
        self.assertEqual(self.book(minutes=60).status_code, 403)
        self.assertEqual(self.book(minutes=30).status_code, 201)

    def test_someone_elses_certification_does_not_count(self):
        other = get_user_model().objects.create_user("other", password="unused-test-pw")
        self.grant(user=other)
        self.assertEqual(self.book().status_code, 403)

    def test_all_requirements_needed_and_only_missing_ones_listed(self):
        lab = Lab.objects.get(pk=RESTRICTED_LAB)
        lab.required_certifications.add("CERT-SOLDER")
        self.grant()
        response = self.book()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["missingCertifications"], ["CERT-SOLDER"])

    def test_certification_check_runs_before_conflict_check(self):
        # A student without the certification learns that, not that the slot is taken.
        Booking.objects.create(user=self.faculty, lab=Lab.objects.get(pk=RESTRICTED_LAB),
                               start=self.start, end=self.start + timedelta(hours=1))
        self.assertEqual(self.book().status_code, 403)


class CertificationApiTests(SkillPassTestCase):
    def test_catalogue_is_public(self):
        response = APIClient().get("/api/v1/certifications/")
        self.assertEqual(response.status_code, 200)
        ids = {cert["id"] for cert in response.json()}
        self.assertEqual(ids, {"CERT-ELEC-BASIC", "CERT-SOLDER", "CERT-ROBOT-ARM", "CERT-3DP"})

    def test_seed_grants_nothing(self):
        call_command("seed_demo", "--demo-user", verbosity=0, stdout=open("/dev/null", "w"))
        self.assertFalse(UserCertification.objects.exists())

    def test_mine_requires_sign_in_and_shows_only_own_records(self):
        self.assertEqual(APIClient().get("/api/v1/certifications/mine/").status_code, 401)
        self.grant()
        self.grant(cert=Certification.objects.get(pk="CERT-SOLDER"), user=self.faculty)
        records = self.client.get("/api/v1/certifications/mine/").json()
        self.assertEqual([r["certification"]["id"] for r in records], ["CERT-ELEC-BASIC"])
        self.assertTrue(records[0]["isValid"])
        self.assertEqual(records[0]["approvedBy"], "faculty")

    def test_request_creates_pending_record_once(self):
        url = "/api/v1/certifications/CERT-SOLDER/request/"
        first = self.client.post(url)
        second = self.client.post(url)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["status"], "pending")
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(UserCertification.objects.count(), 1)

    def test_request_when_already_certified_is_rejected(self):
        self.grant()
        self.assertEqual(self.client.post("/api/v1/certifications/CERT-ELEC-BASIC/request/").status_code, 400)

    def test_request_after_revocation_starts_new_approval(self):
        record = self.grant(status=UserCertification.Status.REVOKED)
        response = self.client.post("/api/v1/certifications/CERT-ELEC-BASIC/request/")
        self.assertEqual(response.json()["status"], "pending")
        record.refresh_from_db()
        self.assertIsNone(record.approved_by)

    def test_faculty_approval_unlocks_booking_with_expiry(self):
        record_id = self.client.post("/api/v1/certifications/CERT-ELEC-BASIC/request/").json()["id"]
        self.assertEqual(self.book().status_code, 403)

        pending = self.faculty_client.get("/api/v1/certification-records/?status=pending").json()
        self.assertEqual([r["id"] for r in pending], [record_id])
        self.assertEqual((pending[0]["username"], pending[0]["studentName"]), ("student", "student"))

        response = self.faculty_client.post(f"/api/v1/certification-records/{record_id}/approve/")
        self.assertEqual(response.status_code, 200)
        record = UserCertification.objects.get(pk=record_id)
        self.assertEqual(record.approved_by, self.faculty)
        self.assertAlmostEqual(record.expires_at - record.approved_at, timedelta(days=365),
                               delta=timedelta(seconds=1))
        self.assertEqual(self.book().status_code, 201)

    def test_revocation_blocks_future_bookings(self):
        record = self.grant()
        response = self.faculty_client.post(f"/api/v1/certification-records/{record.id}/revoke/")
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.revoked_by, self.faculty)
        self.assertEqual(self.book().status_code, 403)

    def test_students_cannot_approve_or_list_records(self):
        record = self.grant(status=UserCertification.Status.PENDING)
        self.assertEqual(self.client.get("/api/v1/certification-records/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/v1/certification-records/{record.id}/approve/").status_code, 403)
        record.refresh_from_db()
        self.assertEqual(record.status, "pending")

    def test_faculty_cannot_approve_their_own_certification(self):
        record = self.grant(status=UserCertification.Status.PENDING, user=self.faculty)
        response = self.faculty_client.post(f"/api/v1/certification-records/{record.id}/approve/")
        self.assertEqual(response.status_code, 403)
        record.refresh_from_db()
        self.assertEqual(record.status, "pending")


class ServiceTests(SkillPassTestCase):
    def test_certification_without_validity_never_expires(self):
        forever = Certification.objects.create(id="CERT-FOREVER", name="Induction")
        record = UserCertification.objects.create(user=self.student, certification=forever)
        services.approve(record, self.faculty)
        self.assertIsNone(record.expires_at)
        self.assertTrue(record.is_valid_at(timezone.now() + timedelta(days=3650)))

    def test_missing_certifications_respects_valid_until(self):
        self.grant(expires_at=self.start)
        required = [self.elec]
        self.assertEqual(services.missing_certifications(self.student, required, self.start), [])
        self.assertEqual(services.missing_certifications(self.student, required, self.start + timedelta(minutes=1)),
                         [self.elec])
