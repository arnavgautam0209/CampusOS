import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from labs.models import Lab


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for faculty approval"
        ACTIVE = "active", "Confirmed"
        DECLINED = "declined", "Declined by faculty"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Not approved in time"

    # Statuses that hold the time slot so nobody else can book it.
    HOLDS_SLOT = (Status.PENDING, Status.ACTIVE)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    lab = models.ForeignKey(Lab, on_delete=models.PROTECT, related_name="bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=200, blank=True, help_text="What the student plans to do (shown to faculty).")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)
    # Set when the student taps their card on the lab's door reader (actual session start).
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_device = models.ForeignKey("devices.Device", null=True, blank=True, on_delete=models.SET_NULL,
                                          related_name="+")

    class Meta:
        ordering = ["start"]
        constraints = [
            models.CheckConstraint(check=Q(end__gt=F("start")), name="booking_end_after_start"),
        ]
        indexes = [models.Index(fields=["lab", "status", "start"])]

    def __str__(self):
        return f"{self.lab_id} {self.start:%Y-%m-%d %H:%M} ({self.status})"
