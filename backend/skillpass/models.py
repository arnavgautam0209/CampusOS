from django.conf import settings
from django.db import models
from django.utils import timezone


class Certification(models.Model):
    """A practical skill that faculty can certify, e.g. soldering safety."""

    id = models.CharField(primary_key=True, max_length=32)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    validity_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="How long an approval lasts. Empty means it never expires."
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserCertification(models.Model):
    """One student's record for one certification. Only staff can approve it."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REVOKED = "revoked", "Revoked"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="certifications")
    certification = models.ForeignKey(Certification, on_delete=models.PROTECT, related_name="holders")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["certification__name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "certification"], name="one_record_per_user_certification"),
        ]

    def __str__(self):
        return f"{self.user} · {self.certification} ({self.status})"

    def is_valid_at(self, moment):
        return self.status == self.Status.APPROVED and (self.expires_at is None or self.expires_at > moment)

    @property
    def is_valid(self):
        return self.is_valid_at(timezone.now())
