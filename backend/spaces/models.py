import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class RoomBooking(models.Model):
    """A SpacePulse reservation of a campus room (classroom, study or meeting room)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired (no check-in)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey("attendance.Classroom", on_delete=models.PROTECT, related_name="bookings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="room_bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    purpose = models.CharField(max_length=120, blank=True)
    attendees = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start"]
        constraints = [
            models.CheckConstraint(check=Q(end__gt=F("start")), name="room_booking_end_after_start"),
            models.CheckConstraint(check=Q(attendees__gte=1), name="room_booking_attendees_at_least_one"),
        ]
        indexes = [models.Index(fields=["room", "status", "start"])]

    def __str__(self):
        return f"{self.room_id} {self.start:%Y-%m-%d %H:%M} ({self.status})"
