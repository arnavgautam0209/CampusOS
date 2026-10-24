"""
SpacePulse seat capacity: how many seats a room has free over a time range,
and which room fits a group best. Deterministic rules, no AI.

A room's capacity never changes. Over a requested range:
- a timetabled class (active timetable) or an exclusive booking makes it fully unavailable;
- otherwise free seats = capacity - the busiest moment of overlapping shared bookings.
Cancelled and expired bookings don't count.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from django.utils import timezone

from .models import RoomBooking, Timetable, TimetableEntry


@dataclass
class Lecture:
    room_id: str
    activity: str
    start: datetime
    end: datetime


@dataclass
class RoomSeats:
    room: object
    free: int                      # seats free for the whole range (0 when blocked)
    peak_booked: int = 0           # most shared seats taken at any moment in the range
    lecture: Optional[Lecture] = None
    exclusive: bool = False        # an exclusive booking overlaps
    bookings: List[RoomBooking] = field(default_factory=list)

    @property
    def blocked_reason(self):
        if self.lecture:
            return (f"Timetabled: {self.lecture.activity} "
                    f"{timezone.localtime(self.lecture.start):%H:%M}–{timezone.localtime(self.lecture.end):%H:%M}")
        if self.exclusive:
            return "Booked for exclusive use"
        return None


def active_timetable():
    return Timetable.objects.filter(status=Timetable.Status.ACTIVE).first()


def lectures_between(start, end, timetable=None, room_ids=None):
    """Timetabled classes overlapping [start, end), as real datetimes. `timetable` defaults to the active one."""
    timetable = timetable if timetable is not None else active_timetable()
    if timetable is None:
        return []
    tz = timezone.get_current_timezone()
    local_start, local_end = timezone.localtime(start, tz), timezone.localtime(end, tz)
    days = []
    day = local_start.date()
    while day <= local_end.date():
        days.append(day)
        day += timedelta(days=1)
    entries = TimetableEntry.objects.filter(timetable=timetable, weekday__in={d.weekday() for d in days})
    if room_ids is not None:
        entries = entries.filter(room_id__in=room_ids)
    lectures = []
    for entry in entries:
        for day in days:
            if day.weekday() != entry.weekday:
                continue
            lecture_start = timezone.make_aware(datetime.combine(day, entry.start), tz)
            lecture_end = timezone.make_aware(datetime.combine(day, entry.end), tz)
            if lecture_start < end and lecture_end > start:
                lectures.append(Lecture(entry.room_id, entry.activity, lecture_start, lecture_end))
    return sorted(lectures, key=lambda lecture: lecture.start)


def overlapping_bookings(start, end, room_ids=None, exclude=None):
    bookings = RoomBooking.objects.filter(status=RoomBooking.Status.ACTIVE, start__lt=end, end__gt=start)
    if room_ids is not None:
        bookings = bookings.filter(room_id__in=room_ids)
    if exclude is not None:
        bookings = bookings.exclude(pk=exclude.pk)
    return list(bookings)


def peak_seats(bookings, start, end):
    """
    The most seats taken at the same moment within [start, end), from shared bookings.
    A sweep over start/end points: a booking that ends exactly when another starts doesn't overlap it.
    """
    points = []
    for booking in bookings:
        if booking.mode != RoomBooking.Mode.SHARED:
            continue
        lo, hi = max(booking.start, start), min(booking.end, end)
        if lo < hi:
            points.append((lo, 1, booking.attendees))
            points.append((hi, 0, -booking.attendees))   # 0 sorts ends before starts at the same instant
    current = peak = 0
    for _, _, change in sorted(points, key=lambda p: (p[0], p[1])):
        current += change
        peak = max(peak, current)
    return peak


def seats_for(rooms, start, end, timetable=None, exclude=None):
    """RoomSeats for each room over [start, end): 3 queries however many rooms."""
    room_ids = [room.id for room in rooms]
    lectures, bookings = {}, {}
    for lecture in lectures_between(start, end, timetable, room_ids):
        lectures.setdefault(lecture.room_id, lecture)
    for booking in overlapping_bookings(start, end, room_ids, exclude):
        bookings.setdefault(booking.room_id, []).append(booking)
    result = {}
    for room in rooms:
        room_bookings = bookings.get(room.id, [])
        lecture = lectures.get(room.id)
        exclusive = any(b.mode == RoomBooking.Mode.EXCLUSIVE for b in room_bookings)
        peak = peak_seats(room_bookings, start, end)
        free = 0 if (lecture or exclusive) else max(0, room.capacity - peak)
        result[room.id] = RoomSeats(room, free, peak, lecture, exclusive, room_bookings)
    return result


def fits(seats, group_size, mode):
    """Can a group of `group_size` book this room in `mode` over the range?"""
    if seats.blocked_reason:
        return False
    if mode == RoomBooking.Mode.EXCLUSIVE:
        return not seats.bookings and group_size <= seats.room.capacity
    return group_size <= seats.free


def why_not(seats, group_size, mode):
    if seats.blocked_reason:
        return seats.blocked_reason
    if mode == RoomBooking.Mode.EXCLUSIVE and seats.bookings:
        return "Other groups have seats booked then"
    if group_size > seats.room.capacity:
        return f"Seats {seats.room.capacity}, too small for {group_size}"
    return f"Only {seats.free} seats free then"


def rank(candidates, group_size, mode):
    """Best fit first: the fewest empty seats left once the group is in, then the smaller room."""
    def leftover(seats):
        return (seats.room.capacity if mode == RoomBooking.Mode.EXCLUSIVE else seats.free) - group_size
    return sorted(candidates, key=lambda s: (leftover(s), s.room.capacity, s.room.id))


def best_alternative(booking, timetables, now=None):
    """
    The best other room for an existing booking that stays free under every timetable in `timetables`
    (e.g. the active one and the one about to replace it). None if nothing fits.
    """
    from attendance.models import Classroom

    rooms = [r for r in Classroom.objects.filter(kind=booking.room.kind, is_bookable=True).exclude(pk=booking.room_id)]
    candidates = []
    per_timetable = [seats_for(rooms, booking.start, booking.end, timetable=t, exclude=booking) for t in timetables]
    for room in rooms:
        options = [seats[room.id] for seats in per_timetable]
        if all(fits(option, booking.attendees, booking.mode) for option in options):
            candidates.append(min(options, key=lambda option: option.free))
    ranked = rank(candidates, booking.attendees, booking.mode)
    return ranked[0].room if ranked else None
