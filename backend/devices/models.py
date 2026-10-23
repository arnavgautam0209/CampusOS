import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def hash_key(raw_key):
    # Keys are long random tokens, so a fast hash is enough (like API keys, unlike passwords).
    return hashlib.sha256(raw_key.encode()).hexdigest()


class Device(models.Model):
    """A campus reader (ESP32 + RFID) that authenticates with its own secret key."""

    id = models.CharField(primary_key=True, max_length=32, help_text="e.g. READER-ROOM-101")
    name = models.CharField(max_length=120)
    classroom = models.ForeignKey(
        "attendance.Classroom", null=True, blank=True, on_delete=models.SET_NULL, related_name="devices",
        help_text="Classroom reader: marks attendance while a session is open in this room.",
    )
    lab = models.ForeignKey(
        "labs.Lab", null=True, blank=True, on_delete=models.SET_NULL, related_name="readers",
        help_text="Lab door reader: checks students in to their booking for this lab.",
    )
    is_active = models.BooleanField(default=True)
    key_hash = models.CharField(max_length=64, blank=True, editable=False)
    key_prefix = models.CharField(max_length=12, blank=True, editable=False,
                                  help_text="First characters of the key, to tell keys apart.")
    key_issued_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(check=Q(classroom__isnull=True) | Q(lab__isnull=True),
                                   name="reader_in_classroom_or_lab_not_both"),
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"

    def issue_key(self):
        """Creates a new key, replacing any old one. Returns the raw key: show it once, never store it."""
        raw_key = "dev_" + secrets.token_urlsafe(32)
        self.key_hash = hash_key(raw_key)
        self.key_prefix = raw_key[:12]
        self.key_issued_at = timezone.now()
        self.save(update_fields=["key_hash", "key_prefix", "key_issued_at"])
        return raw_key


class ScanEvent(models.Model):
    """Every scan a reader sends, accepted or not, for auditing and troubleshooting."""

    class Result(models.TextChoices):
        MARKED = "marked", "Attendance marked"
        DUPLICATE = "duplicate", "Already marked"
        UNKNOWN_CARD = "unknown_card", "Unknown card"
        NO_SESSION = "no_session", "No open session"
        WRONG_CLASSROOM = "wrong_classroom", "Wrong classroom or lab"
        GRANTED = "granted", "Lab access granted"
        ALREADY_CHECKED_IN = "already_checked_in", "Already checked in"
        DENIED = "denied", "Lab access denied"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="scans")
    uid = models.CharField(max_length=20)
    classroom_id_sent = models.CharField(max_length=32, verbose_name="location sent",
                                         help_text="The classroomId or labId the reader sent.")
    result = models.CharField(max_length=20, choices=Result.choices)
    reason = models.CharField(max_length=32, blank=True, help_text="Why lab access was denied.")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    session = models.ForeignKey("attendance.AttendanceSession", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="+")
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.device_id} {self.uid} → {self.result}"
