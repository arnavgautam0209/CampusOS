"""
SkillPass rules. These are deterministic checks against approved records:
no AI or client-side code can grant or bypass a certification.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from .models import UserCertification


class CertificationRequired(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "certification_required"

    def __init__(self, missing, subject="This lab"):
        names = ", ".join(cert.name for cert in missing)
        super().__init__({
            "detail": f"{subject} requires certification: {names}. Ask faculty to approve your training in SkillPass.",
            "missingCertifications": [cert.id for cert in missing],
        })


def missing_certifications(user, required, valid_until):
    """Certifications in `required` that `user` doesn't hold approved up to `valid_until`.

    A session runs up to (not past) its end, so expiring exactly at `valid_until` is enough.
    """
    held = set(
        UserCertification.objects.filter(user=user, status=UserCertification.Status.APPROVED)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=valid_until))
        .values_list("certification_id", flat=True)
    )
    return [cert for cert in required if cert.id not in held]


def ensure_lab_access(user, lab, valid_until):
    """Raises CertificationRequired unless the user can use `lab` until `valid_until`."""
    missing = missing_certifications(user, lab.required_certifications.order_by("name"), valid_until)
    if missing:
        raise CertificationRequired(missing)


def request_certification(user, certification):
    record, created = UserCertification.objects.get_or_create(user=user, certification=certification)
    if created or record.status == UserCertification.Status.PENDING:
        return record
    if record.is_valid:
        raise ValidationError({"certification": "You already hold this certification."})
    # Revoked or expired: start a fresh approval request.
    record.status = UserCertification.Status.PENDING
    record.approved_by = record.approved_at = record.expires_at = None
    record.revoked_by = record.revoked_at = None
    record.save()
    return record


def approve(record, approver):
    if not approver.is_staff:
        raise PermissionDenied("Only faculty can approve certifications.")
    if approver.pk == record.user_id:
        raise PermissionDenied("You can't approve your own certification.")
    now = timezone.now()
    validity = record.certification.validity_days
    record.status = UserCertification.Status.APPROVED
    record.approved_by = approver
    record.approved_at = now
    record.expires_at = now + timedelta(days=validity) if validity else None
    record.revoked_by = record.revoked_at = None
    record.save()
    return record


def revoke(record, revoker):
    if not revoker.is_staff:
        raise PermissionDenied("Only faculty can revoke certifications.")
    if record.status == UserCertification.Status.REVOKED:
        raise ValidationError({"status": "This certification is already revoked."})
    record.status = UserCertification.Status.REVOKED
    record.revoked_by = revoker
    record.revoked_at = timezone.now()
    record.save()
    return record
