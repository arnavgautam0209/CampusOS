"""
SpacePulse booking rules. The server is the source of truth for room
availability; the app only shows what these functions allow.
"""

from datetime import datetime, time, timedelta

from django.db import connection, transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from attendance.models import AttendanceSession, Classroom
from bookings.services import MAX_DURATION_MINUTES, MIN_DURATION_MINUTES

from . import capacity
from .models import RoomBooking

MAX_GROUP_SIZE = 500

CHECK_IN_OPENS = timedelta(minutes=10)   # before the start
NO_SHOW_AFTER = timedelta(minutes=15)    # after the start, an un-checked-in booking expires
DAY_START, DAY_END = time(8, 0), time(20, 0)


class RoomConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "That room is already booked for part of that time."
    default_code = "room_conflict"


def parse_mode(raw, default=RoomBooking.Mode.EXCLUSIVE):
    if raw in (None, ""):
        return default
    if raw not in RoomBooking.Mode.values:
        raise ValidationError({"mode": "Use shared or exclusive."})
    return raw


def check_request(start, duration_minutes, group_size, now):
    if not (MIN_DURATION_MINUTES <= duration_minutes <= MAX_DURATION_MINUTES):
        raise ValidationError({"durationMinutes": f"Must be between {MIN_DURATION_MINUTES} and "
                                                  f"{MAX_DURATION_MINUTES} minutes."})
    if start <= now:
        raise ValidationError({"start": "Choose a future start time."})
    if start > now + timedelta(days=30):
        raise ValidationError({"start": "Rooms can be booked up to 30 days ahead."})
    if not (1 <= group_size <= MAX_GROUP_SIZE):
        raise ValidationError({"attendees": f"Group size must be between 1 and {MAX_GROUP_SIZE}."})


def lock_room(room_id):
    """
    Serialise bookings for one room. PostgreSQL locks the row (SELECT … FOR UPDATE). SQLite ignores
    FOR UPDATE, so a no-op UPDATE takes SQLite's database write lock first: a second booking waits
    until this transaction commits instead of reading the same free seats.
    """
    if connection.vendor == "sqlite":
        Classroom.objects.filter(pk=room_id).update(capacity=F("capacity"))
    return Classroom.objects.select_for_update().filter(pk=room_id).first()


def release_no_shows(now=None):
    """Expire bookings nobody checked in to, so the room becomes free again."""
    now = now or timezone.now()
    return RoomBooking.objects.filter(status=RoomBooking.Status.ACTIVE, checked_in_at__isnull=True,
                                      start__lt=now - NO_SHOW_AFTER).update(status=RoomBooking.Status.EXPIRED)


def book_room(user, room_id, start, duration_minutes, attendees=1, purpose="", now=None,
              mode=RoomBooking.Mode.EXCLUSIVE):
    """
    Exclusive: the whole room, nothing else may overlap. Shared: the group's seats must be free for the
    whole range (busiest moment counted). Either way a timetabled class blocks the room.
    """
    now = now or timezone.now()
    check_request(start, duration_minutes, attendees, now)
    end = start + timedelta(minutes=duration_minutes)
    release_no_shows(now)

    with transaction.atomic():
        room = lock_room(room_id)
        if room is None:
            raise NotFound("Room not found.")
        if not room.is_bookable and not user.is_staff:
            raise PermissionDenied(f"{room.name} is timetabled; ask faculty to book it.")
        if attendees > room.capacity:
            raise ValidationError({"attendees": f"{room.name} seats {room.capacity}."})
        seats = capacity.seats_for([room], start, end)[room.id]
        if seats.lecture:
            raise RoomConflict(f"{room.name} has a class then ({seats.blocked_reason.split(': ', 1)[1]}).")
        if mode == RoomBooking.Mode.EXCLUSIVE and seats.bookings:
            raise RoomConflict()
        if mode == RoomBooking.Mode.SHARED:
            if seats.exclusive:
                raise RoomConflict(f"{room.name} is booked for exclusive use for part of that time.")
            if attendees > seats.free:
                raise RoomConflict(f"Only {seats.free} of {room.capacity} seats in {room.name} are free for the "
                                   f"whole time; your group needs {attendees}.")
        return RoomBooking.objects.create(room=room, user=user, start=start, end=end, attendees=attendees,
                                          mode=mode, purpose=(purpose or "").strip()[:120])


def recommend(user, start, duration_minutes, group_size, mode=RoomBooking.Mode.SHARED, kind="classroom", now=None):
    """
    Rooms a group can book over the range, best fit first (fewest seats left empty), plus the rooms
    that don't work and why. Uses real free seats at that time, not total capacity.
    """
    now = now or timezone.now()
    check_request(start, duration_minutes, group_size, now)
    end = start + timedelta(minutes=duration_minutes)
    release_no_shows(now)
    rooms = Classroom.objects.order_by("id")
    if kind != "all":
        rooms = rooms.filter(kind=kind)
    if not user.is_staff:
        rooms = rooms.filter(is_bookable=True)
    rooms = list(rooms)
    seats = capacity.seats_for(rooms, start, end)
    eligible = capacity.rank([s for s in seats.values() if capacity.fits(s, group_size, mode)], group_size, mode)
    unavailable = [s for s in seats.values() if not capacity.fits(s, group_size, mode)]
    return {"start": start, "end": end, "group_size": group_size, "mode": mode, "eligible": eligible,
            "unavailable": sorted(unavailable, key=lambda s: s.room.id), "timetable": capacity.active_timetable()}


def cancel(booking, user, note=""):
    """Cancelling releases the group's seats at once (only active bookings take seats)."""
    if booking.user_id != user.pk and not user.is_staff:
        raise PermissionDenied("Only the person who booked can cancel.")
    if booking.status != RoomBooking.Status.ACTIVE:
        raise ValidationError({"status": "Only active bookings can be cancelled."})
    if booking.end <= timezone.now():
        raise ValidationError({"status": "This booking has already ended."})
    booking.status = RoomBooking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.note = note[:240]
    booking.save(update_fields=["status", "cancelled_at", "note"])
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
