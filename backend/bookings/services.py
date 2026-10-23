"""
Booking rules. The server is the source of truth: the iOS app may pre-check
these for a nicer UX, but only this module decides whether a booking exists.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from labs.models import Lab
from skillpass.services import ensure_lab_access

from .models import Booking

MIN_DURATION_MINUTES = 15
MAX_DURATION_MINUTES = 240


class BookingConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This lab already has an overlapping reservation."
    default_code = "booking_conflict"


def create_booking(user, lab_id, start, duration_minutes):
    if not (MIN_DURATION_MINUTES <= duration_minutes <= MAX_DURATION_MINUTES):
        raise ValidationError(
            {"durationMinutes": f"Must be between {MIN_DURATION_MINUTES} and {MAX_DURATION_MINUTES} minutes."}
        )
    if start <= timezone.now():
        raise ValidationError({"start": "Choose a future start time."})

    end = start + timedelta(minutes=duration_minutes)

    with transaction.atomic():
        # Locking the lab row serialises concurrent bookings for the same lab
        # on PostgreSQL. SQLite ignores the lock but only allows one writer.
        lab = Lab.objects.select_for_update().filter(pk=lab_id).first()
        if lab is None:
            raise NotFound("Lab not found.")
        if not lab.is_open_for_booking:
            raise ValidationError({"labID": "This lab is not accepting bookings."})
        # SkillPass: certifications must stay valid for the whole session.
        ensure_lab_access(user, lab, valid_until=end)

        overlaps = Booking.objects.filter(
            lab=lab, status=Booking.Status.ACTIVE, start__lt=end, end__gt=start
        ).exists()
        if overlaps:
            raise BookingConflict()

        return Booking.objects.create(user=user, lab=lab, start=start, end=end)


def cancel_booking(booking):
    if booking.status != Booking.Status.ACTIVE:
        raise ValidationError({"status": "Only active bookings can be cancelled."})
    if booking.end <= timezone.now():
        raise ValidationError({"status": "This booking has already ended."})
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])
    return booking
