"""
Booking rules. The server is the source of truth: the iOS app may pre-check
these for a nicer UX, but only this module decides whether a booking exists.
"""

from datetime import timedelta
from typing import NamedTuple, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

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


def expire_stale_requests(now=None):
    """Requests nobody approved before their start time can't be used any more; free the slot."""
    now = now or timezone.now()
    return Booking.objects.filter(status=Booking.Status.PENDING, start__lte=now).update(
        status=Booking.Status.EXPIRED)


def create_booking(user, lab_id, start, duration_minutes, purpose=""):
    """
    Students' bookings for labs that require approval start as PENDING (holding the
    slot) until faculty approve them; staff bookings and other labs are confirmed.
    """
    if not (MIN_DURATION_MINUTES <= duration_minutes <= MAX_DURATION_MINUTES):
        raise ValidationError(
            {"durationMinutes": f"Must be between {MIN_DURATION_MINUTES} and {MAX_DURATION_MINUTES} minutes."}
        )
    if start <= timezone.now():
        raise ValidationError({"start": "Choose a future start time."})

    end = start + timedelta(minutes=duration_minutes)
    expire_stale_requests()

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

        # Pending requests hold the slot too, so two students can't request the same time.
        overlaps = Booking.objects.filter(
            lab=lab, status__in=Booking.HOLDS_SLOT, start__lt=end, end__gt=start
        ).exists()
        if overlaps:
            raise BookingConflict()

        needs_approval = lab.requires_approval and not user.is_staff
        return Booking.objects.create(
            user=user, lab=lab, start=start, end=end, purpose=(purpose or "").strip()[:200],
            status=Booking.Status.PENDING if needs_approval else Booking.Status.ACTIVE)


def cancel_booking(booking):
    """Cancels a confirmed booking or withdraws a pending request."""
    if booking.status not in Booking.HOLDS_SLOT:
        raise ValidationError({"status": "Only active bookings or pending requests can be cancelled."})
    if booking.end <= timezone.now():
        raise ValidationError({"status": "This booking has already ended."})
    if booking.checked_in_at:
        raise ValidationError({"status": "You've already checked in to this booking."})
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])
    return booking



def _ensure_reviewable(booking, reviewer, now):
    if not reviewer.is_staff:
        raise PermissionDenied("Only faculty can review lab requests.")
    if booking.user_id == reviewer.pk:
        raise PermissionDenied("You can't approve your own request.")
    expire_stale_requests(now)
    booking.refresh_from_db()
    if booking.status == Booking.Status.EXPIRED:
        raise ValidationError({"status": "This request expired: its start time has passed."})
    if booking.status != Booking.Status.PENDING:
        raise ValidationError({"status": "This request has already been decided or withdrawn."})


def approve_booking(booking, reviewer, note="", now=None):
    """Confirms a pending request. Re-checks SkillPass in case a certification changed since."""
    now = now or timezone.now()
    with transaction.atomic():
        _ensure_reviewable(booking, reviewer, now)
        ensure_lab_access(booking.user, booking.lab, valid_until=booking.end)
        booking.status = Booking.Status.ACTIVE
        booking.decided_by, booking.decided_at = reviewer, now
        booking.decision_note = (note or "").strip()[:200]
        booking.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    return booking


def decline_booking(booking, reviewer, note="", now=None):
    """Declines a pending request and frees the slot."""
    now = now or timezone.now()
    with transaction.atomic():
        _ensure_reviewable(booking, reviewer, now)
        booking.status = Booking.Status.DECLINED
        booking.decided_by, booking.decided_at = reviewer, now
        booking.decision_note = (note or "").strip()[:200]
        booking.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
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
            awaiting = Booking.objects.filter(user=user, lab=lab, status=Booking.Status.PENDING,
                                              start__lte=now + CHECK_IN_EARLY, end__gt=now).first()
            if awaiting:
                return CheckIn("denied", "Your request is still waiting for faculty approval.", booking=awaiting,
                               reason="awaiting_approval")
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
