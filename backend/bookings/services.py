"""
Booking rules. The server is the source of truth: the iOS app may pre-check
these for a nicer UX, but only this module decides whether a booking exists.
"""

from datetime import timedelta
from typing import NamedTuple, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from labs.models import Lab
from skillpass.services import ensure_lab_access, missing_certifications

from .models import Booking

MIN_DURATION_MINUTES = 15
MAX_DURATION_MINUTES = 240
CHECK_IN_EARLY = timedelta(minutes=10)


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
    if booking.checked_in_at:
        raise ValidationError({"status": "You've already checked in to this booking."})
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])
    return booking


class CheckIn(NamedTuple):
    result: str                      # "granted", "already_checked_in" or "denied"
    message: str
    booking: Optional[Booking] = None
    reason: str = ""                 # set when denied
    missing: Tuple = ()              # certifications missing, when that's the reason


def check_in(user, lab, device=None, now=None):
    """
    A student tapped their card on a lab's door reader. Grants access only with
    their own active booking for this lab (from CHECK_IN_EARLY before the start
    until the end) and every required certification valid until it ends.
    """
    now = now or timezone.now()
    if not lab.is_open_for_booking:
        return CheckIn("denied", f"{lab.name} is closed.", reason="lab_closed")

    with transaction.atomic():
        booking = (Booking.objects.select_for_update()
                   .filter(user=user, lab=lab, status=Booking.Status.ACTIVE,
                           start__lte=now + CHECK_IN_EARLY, end__gt=now)
                   .order_by("start").first())
        if booking is None:
            later = (Booking.objects.filter(user=user, lab=lab, status=Booking.Status.ACTIVE,
                                            start__gt=now + CHECK_IN_EARLY,
                                            start__date=timezone.localdate(now))
                     .order_by("start").first())
            if later:
                opens = timezone.localtime(later.start - CHECK_IN_EARLY)
                return CheckIn("denied", f"Too early. Check in from {opens:%H:%M}.", booking=later,
                               reason="too_early")
            return CheckIn("denied", f"No booking for {lab.name} right now.", reason="no_booking")

        missing = missing_certifications(user, lab.required_certifications.order_by("name"), booking.end)
        if missing:
            names = ", ".join(cert.name for cert in missing)
            return CheckIn("denied", f"Needs SkillPass: {names}.", booking=booking,
                           reason="certification_required", missing=tuple(missing))

        until = f"{timezone.localtime(booking.end):%H:%M}"
        if booking.checked_in_at:
            return CheckIn("already_checked_in", f"Already checked in until {until}.", booking=booking)
        booking.checked_in_at = now
        booking.checked_in_device = device
        booking.save(update_fields=["checked_in_at", "checked_in_device"])
        return CheckIn("granted", f"Access granted until {until}.", booking=booking)
