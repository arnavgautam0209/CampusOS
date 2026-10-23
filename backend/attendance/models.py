from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

# RC522/PN532 UIDs are 4, 7 or 10 bytes, stored as uppercase hex without separators.
UID_PATTERN = r"^(?:[0-9A-F]{8}|[0-9A-F]{14}|[0-9A-F]{20})$"
uid_validator = RegexValidator(UID_PATTERN, "Use 4, 7 or 10 bytes of uppercase hex, e.g. 04A1B2C3.")


class Classroom(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.id})"


class CampusCard(models.Model):
    """
    Links a card UID to a student. Prototype limitation: a UID only proves a
    card was present, not who held it, and UIDs can be cloned.
    """

    uid = models.CharField(max_length=20, unique=True, validators=[uid_validator])
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="campus_cards")
    is_active = models.BooleanField(default=True, help_text="Untick for lost or replaced cards.")
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uid"]

    def __str__(self):
        return f"{self.uid} → {self.user}"

    def save(self, *args, **kwargs):
        self.uid = self.uid.upper()
        super().save(*args, **kwargs)


class AttendanceSession(models.Model):
    """Opened by faculty; readers in the classroom can only mark attendance while it's open."""

    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="sessions")
    title = models.CharField(max_length=120, help_text="e.g. 'CS201 Lecture 5'")
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["classroom"], condition=Q(closed_at__isnull=True),
                name="one_open_session_per_classroom",
                violation_error_message="This classroom already has an open attendance session.",
            ),
        ]

    def __str__(self):
        return f"{self.title} · {self.classroom_id}"

    @property
    def is_open(self):
        return self.closed_at is None


class AttendanceRecord(models.Model):
    class Source(models.TextChoices):
        CARD = "card", "Card scan"
        MANUAL = "manual", "Added by faculty"

    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance")
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.CARD)
    card = models.ForeignKey(CampusCard, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    device = models.ForeignKey("devices.Device", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+")
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["marked_at"]
        constraints = [
            models.UniqueConstraint(fields=["session", "student"], name="one_record_per_student_per_session"),
        ]

    def __str__(self):
        return f"{self.student} @ {self.session}"
