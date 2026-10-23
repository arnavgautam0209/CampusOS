import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from labs.models import Lab


class Booking(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    lab = models.ForeignKey(Lab, on_delete=models.PROTECT, related_name="bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start"]
        constraints = [
            models.CheckConstraint(check=Q(end__gt=F("start")), name="booking_end_after_start"),
        ]
        indexes = [models.Index(fields=["lab", "status", "start"])]

    def __str__(self):
        return f"{self.lab_id} {self.start:%Y-%m-%d %H:%M} ({self.status})"
