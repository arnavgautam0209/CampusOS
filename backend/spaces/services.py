"""
SpacePulse booking rules. The server is the source of truth for room
availability; the app only shows what these functions allow.
"""

from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from attendance.models import AttendanceSession, Classroom
from bookings.services import MAX_DURATION_MINUTES, MIN_DURATION_MINUTES

from .models import RoomBooking

CHECK_IN_OPENS = timedelta(minutes=10)   # before the start
NO_SHOW_AFTER = timedelta(minutes=15)    # after the start, an un-checked-in booking expires
DAY_START, DAY_END = time(8, 0), time(20, 0)


class RoomConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "That room is already booked for part of that time."
    default_code = "room_conflict"


def release_no_shows(now=None):
    """Expire bookings nobody checked in to, so the room becomes free again."""
    now = now or timezone.now()
    return RoomBooking.objects.filter(status=RoomBooking.Status.ACTIVE, checked_in_at__isnull=True,
                                      start__lt=now - NO_SHOW_AFTER).update(status=RoomBooking.Status.EXPIRED)


def book_room(user, room_id, start, duration_minutes, attendees=1, purpose="", now=None):
    now = now or timezone.now()
    if not (MIN_DURATION_MINUTES <= duration_minutes <= MAX_DURATION_MINUTES):
        raise ValidationError({"durationMinutes": f"Must be between {MIN_DURATION_MINUTES} and "
                                                  f"{MAX_DURATION_MINUTES} minutes."})
    if start <= now:
        raise ValidationError({"start": "Choose a future start time."})
    if start > now + timedelta(days=30):
        raise ValidationError({"start": "Rooms can be booked up to 30 days ahead."})
    if attendees < 1:
        raise ValidationError({"attendees": "At least 1 person."})
    end = start + timedelta(minutes=duration_minutes)
    release_no_shows(now)

    with transaction.atomic():
        # Locking the room row serialises bookings for the same room (PostgreSQL).
        room = Classroom.objects.select_for_update().filter(pk=room_id).first()
        if room is None:
            raise NotFound("Room not found.")
        if not room.is_bookable and not user.is_staff:
            raise PermissionDenied(f"{room.name} is timetabled; ask faculty to book it.")
        if attendees > room.capacity:
            raise ValidationError({"attendees": f"{room.name} seats {room.capacity}."})
        clash = RoomBooking.objects.filter(room=room, status=RoomBooking.Status.ACTIVE,
                                           start__lt=end, end__gt=start).exists()
        if clash:
            raise RoomConflict()
        return RoomBooking.objects.create(room=room, user=user, start=start, end=end, attendees=attendees,
                                          purpose=(purpose or "").strip()[:120])


def cancel(booking, user):
    if booking.user_id != user.pk and not user.is_staff:
        raise PermissionDenied("Only the person who booked can cancel.")
    if booking.status != RoomBooking.Status.ACTIVE:
        raise ValidationError({"status": "Only active bookings can be cancelled."})
    if booking.end <= timezone.now():
        raise ValidationError({"status": "This booking has already ended."})
    booking.status = RoomBooking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])
    return booking


def check_in(booking, user, now=None):
    now = now or timezone.now()
    release_no_shows(now)
    booking.refresh_from_db()
    if booking.user_id != user.pk:
        raise PermissionDenied("Only the person who booked can check in.")
    if booking.status == RoomBooking.Status.EXPIRED:
        raise ValidationError({"status": "Check-in closed 15 minutes after the start, so the room was released."})
    if booking.status != RoomBooking.Status.ACTIVE:
        raise ValidationError({"status": "This booking was cancelled."})
    if booking.checked_in_at:
        return booking
    if now < booking.start - CHECK_IN_OPENS:
        opens = timezone.localtime(booking.start - CHECK_IN_OPENS)
        raise ValidationError({"status": f"Check-in opens at {opens:%H:%M}."})
    booking.checked_in_at = now
    booking.save(update_fields=["checked_in_at"])
    return booking


def day_bounds(day):
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(day, DAY_START), tz),
            timezone.make_aware(datetime.combine(day, DAY_END), tz))


def rooms_in_class_now(now=None):
    """Rooms with an open attendance session (a class is running)."""
    return set(AttendanceSession.objects.filter(closed_at__isnull=True).values_list("classroom_id", flat=True))


def utilization(days=7, now=None):
    """Per room over the last `days` days: bookings, booked hours, no-shows, % of 08:00-20:00 used."""
    now = now or timezone.now()
    release_no_shows(now)
    since = now - timedelta(days=days)
    open_hours = days * (DAY_END.hour - DAY_START.hour)
    rows = []
    for room in Classroom.objects.order_by("id"):
        bookings = RoomBooking.objects.filter(room=room, start__gte=since, start__lt=now).exclude(
            status=RoomBooking.Status.CANCELLED)
        used = bookings.filter(Q(checked_in_at__isnull=False) | Q(status=RoomBooking.Status.ACTIVE))
        hours = sum((b.end - b.start).total_seconds() for b in used) / 3600
        counts = bookings.aggregate(total=Count("id"),
                                    no_shows=Count("id", filter=Q(status=RoomBooking.Status.EXPIRED)))
        rows.append({
            "roomId": room.id,
            "roomName": room.name,
            "bookings": counts["total"],
            "noShows": counts["no_shows"],
            "bookedHours": round(hours, 1),
            "utilizationPct": round(100 * hours / open_hours) if open_hours else 0,
        })
    return rows
