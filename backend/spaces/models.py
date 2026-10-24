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

    class Mode(models.TextChoices):
        # Shared: the group takes `attendees` seats and other groups can share the room.
        SHARED = "shared", "Shared study"
        # Exclusive: the whole room, no other booking may overlap.
        EXCLUSIVE = "exclusive", "Exclusive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey("attendance.Classroom", on_delete=models.PROTECT, related_name="bookings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="room_bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    purpose = models.CharField(max_length=120, blank=True)
    attendees = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.EXCLUSIVE)
    note = models.CharField(max_length=240, blank=True,
                            help_text="Set when faculty move or cancel the booking, e.g. because of a new timetable.")
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


class Timetable(models.Model):
    """A version of the weekly class timetable. Exactly one is active; older ones are kept for audit and rollback."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Uploaded, not active"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Previously active"

    version = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    source_filename = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["status"], condition=Q(status="active"), name="one_active_timetable",
                                    violation_error_message="Another timetable is already active."),
        ]

    def __str__(self):
        return f"v{self.version} {self.name} ({self.status})"


class TimetableEntry(models.Model):
    """A weekly class: the room is occupied every such weekday between start and end (local time)."""

    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name="entries")
    weekday = models.PositiveSmallIntegerField(help_text="0 = Monday … 6 = Sunday")
    start = models.TimeField()
    end = models.TimeField()
    room = models.ForeignKey("attendance.Classroom", on_delete=models.PROTECT, related_name="timetable_entries")
    activity = models.CharField(max_length=120)
    row = models.PositiveIntegerField(default=0, help_text="Line in the uploaded CSV")

    class Meta:
        ordering = ["weekday", "start", "room_id"]
        constraints = [
            models.CheckConstraint(check=Q(end__gt=F("start")), name="timetable_entry_end_after_start"),
            models.CheckConstraint(check=Q(weekday__lte=6), name="timetable_entry_weekday_range"),
        ]
        indexes = [models.Index(fields=["timetable", "weekday"])]

    def __str__(self):
        return f"{self.weekday} {self.start:%H:%M}-{self.end:%H:%M} {self.room_id} {self.activity}"


class TimetableEvent(models.Model):
    """Audit log: uploads, activations, and bookings faculty cancelled or moved because of a timetable."""

    class Action(models.TextChoices):
        SEEDED = "seeded", "Seeded"
        UPLOADED = "uploaded", "Uploaded"
        ACTIVATED = "activated", "Activated"
        BOOKING_CANCELLED = "booking_cancelled", "Booking cancelled"
        BOOKING_REASSIGNED = "booking_reassigned", "Booking moved to another room"

    timetable = models.ForeignKey(Timetable, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    booking = models.ForeignKey(RoomBooking, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=32, choices=Action.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
