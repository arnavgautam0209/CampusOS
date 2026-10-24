"""
SpacePulse timetables: CSV upload and validation, preview against the active
timetable, conflicts with existing bookings, activation and conflict resolution.

Activation replaces the active timetable (the old one is archived, never deleted,
so it can be activated again to roll back). It's refused while any upcoming
booking would clash with the new timetable: faculty move or cancel those
bookings first, each logged in TimetableEvent.

CSV columns (header row required, any order, case-insensitive):
    day,start,end,room_id,activity
    Monday,09:00,10:00,ECE-101,Digital Electronics
"""

import csv
import io
from datetime import datetime, time

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from attendance.models import Classroom
from attendance.services import display_name

from . import capacity
from .models import RoomBooking, Timetable, TimetableEntry, TimetableEvent

REQUIRED_COLUMNS = ["day", "start", "end", "room_id", "activity"]
COLUMN_ALIASES = {"room": "room_id", "classroom": "room_id", "classroom_id": "room_id", "weekday": "day",
                  "subject": "activity", "scheduled_activity": "activity", "start_time": "start",
                  "end_time": "end"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_NAMES = [d.title() for d in DAYS]
EARLIEST, LATEST = time(6, 0), time(22, 0)
MAX_ROWS = 2000
MAX_BYTES = 200_000


class InvalidTimetable(ValidationError):
    """400 with {"detail": "...", "errors": [{"row": 3, "message": "..."}]}."""

    def __init__(self, errors, detail="The timetable has problems; nothing was saved."):
        super().__init__(detail)
        # Set directly: DRF would otherwise turn every value, including row numbers, into strings.
        self.detail = {"detail": detail, "errors": errors}


class ActivationBlocked(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "timetable_conflicts"


def _parse_day(raw):
    text = raw.strip().lower()
    for index, day in enumerate(DAYS):
        if text in (day, day[:3]):
            return index
    return None


def _parse_time(raw):
    """'09:00', '9:00', '14:30:00', '2:30 PM' → time; None if it isn't a time."""
    text = raw.strip().replace(".", ":").upper()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def parse_csv(text):
    """
    Returns a list of row dicts {row, weekday, start, end, room_id, activity}, or raises InvalidTimetable
    listing every problem by CSV line number. All-or-nothing: one bad row rejects the file.
    """
    if not text or not text.strip():
        raise InvalidTimetable([], "The file is empty.")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise InvalidTimetable([], f"The file is larger than {MAX_BYTES // 1000} KB.")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise InvalidTimetable([], "The file has no header row.")
    columns = {}
    for name in reader.fieldnames:
        key = (name or "").strip().lower().replace(" ", "_")
        columns[COLUMN_ALIASES.get(key, key)] = name
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise InvalidTimetable([], f"Missing column(s): {', '.join(missing)}. "
                                   f"The header must be: {','.join(REQUIRED_COLUMNS)}")

    rooms = {room.id.upper(): room.id for room in Classroom.objects.all()}
    rows, errors, seen = [], [], {}
    for line, record in enumerate(reader, start=2):
        if line - 1 > MAX_ROWS:
            errors.append({"row": line, "message": f"More than {MAX_ROWS} rows."})
            break
        value = {c: (record.get(columns[c]) or "").strip() for c in REQUIRED_COLUMNS}
        if not any(value.values()):
            continue   # blank line
        problems = []
        weekday = _parse_day(value["day"])
        if weekday is None:
            problems.append(f"Unknown day \"{value['day']}\" (use Monday … Sunday)")
        start, end = _parse_time(value["start"]), _parse_time(value["end"])
        if start is None:
            problems.append(f"Start \"{value['start']}\" isn't a time like 09:00")
        if end is None:
            problems.append(f"End \"{value['end']}\" isn't a time like 10:00")
        if start and end:
            if end <= start:
                problems.append("End must be after start")
            elif start < EARLIEST or end > LATEST:
                problems.append(f"Classes must be between {EARLIEST:%H:%M} and {LATEST:%H:%M}")
        room_id = rooms.get(value["room_id"].upper())
        if not value["room_id"]:
            problems.append("Room is missing")
        elif room_id is None:
            problems.append(f"Unknown room \"{value['room_id']}\"")
        if not value["activity"]:
            problems.append("Activity is missing")
        elif len(value["activity"]) > 120:
            problems.append("Activity is longer than 120 characters")
        if problems:
            errors.append({"row": line, "message": "; ".join(problems)})
            continue
        # The same room can't hold two classes at once.
        for other in seen.get((room_id, weekday), []):
            if start < other["end"] and other["start"] < end:
                errors.append({"row": line, "message": f"{room_id} already has \"{other['activity']}\" on "
                                                       f"{DAY_NAMES[weekday]} {other['start']:%H:%M}–"
                                                       f"{other['end']:%H:%M} (row {other['row']})"})
                break
        else:
            row = {"row": line, "weekday": weekday, "start": start, "end": end, "room_id": room_id,
                   "activity": value["activity"]}
            seen.setdefault((room_id, weekday), []).append(row)
            rows.append(row)
    if errors:
        raise InvalidTimetable(errors)
    if not rows:
        raise InvalidTimetable([], "The file has a header but no classes.")
    return rows


def require_staff(user):
    if not user.is_staff:
        raise PermissionDenied("Only faculty can manage timetables.")


@transaction.atomic
def upload(user, name, text, filename="", action=TimetableEvent.Action.UPLOADED):
    """Validates the CSV and stores it as a new draft version. It isn't used until activated."""
    rows = parse_csv(text)
    name = (name or "").strip() or (filename or "").rsplit(".", 1)[0] or "Uploaded timetable"
    version = (Timetable.objects.aggregate(v=Max("version"))["v"] or 0) + 1
    timetable = Timetable.objects.create(version=version, name=name[:120], source_filename=(filename or "")[:200],
                                         uploaded_by=user if user and user.pk else None)
    TimetableEntry.objects.bulk_create([
        TimetableEntry(timetable=timetable, weekday=r["weekday"], start=r["start"], end=r["end"],
                       room_id=r["room_id"], activity=r["activity"], row=r["row"]) for r in rows])
    TimetableEvent.objects.create(timetable=timetable, action=action, actor=timetable.uploaded_by,
                                  detail=f"{len(rows)} classes from {filename or 'upload'}")
    return timetable


def _slots(timetable):
    if timetable is None:
        return {}
    return {(e.weekday, e.start, e.end, e.room_id): e for e in timetable.entries.all()}


def preview(timetable):
    """What changes if `timetable` replaces the active one: rooms that become occupied or free."""
    active = capacity.active_timetable()
    old = _slots(active if active and active.pk != timetable.pk else None)
    new = _slots(timetable)
    changes = []
    for key in sorted(set(old) | set(new), key=lambda k: (k[0], k[1], k[3])):
        weekday, start, end, room_id = key
        before, after = old.get(key), new.get(key)
        if before and after and before.activity == after.activity:
            continue
        change = "occupied" if not before else "freed" if not after else "activity_changed"
        changes.append({"day": DAY_NAMES[weekday], "weekday": weekday, "start": f"{start:%H:%M}",
                        "end": f"{end:%H:%M}", "roomId": room_id, "change": change,
                        "before": before.activity if before else None, "after": after.activity if after else None})
    return {"against": active if active and active.pk != timetable.pk else None, "changes": changes}


def conflicts(timetable, now=None):
    """Upcoming active bookings that would overlap a class in `timetable` (bookings are at most 30 days out)."""
    now = now or timezone.now()
    bookings = (RoomBooking.objects.filter(status=RoomBooking.Status.ACTIVE, end__gt=now)
                .select_related("room", "user").order_by("start"))
    found = []
    for booking in bookings:
        lectures = capacity.lectures_between(booking.start, booking.end, timetable, [booking.room_id])
        if lectures:
            found.append((booking, lectures[0]))
    return found


def conflict_json(timetable, now=None):
    active = capacity.active_timetable()
    result = []
    for booking, lecture in conflicts(timetable, now):
        others = [t for t in (active, timetable) if t is not None]
        alternative = capacity.best_alternative(booking, others, now)
        result.append({
            "bookingId": str(booking.id),
            "roomId": booking.room_id,
            "roomName": booking.room.name,
            "start": booking.start.isoformat(),
            "end": booking.end.isoformat(),
            "attendees": booking.attendees,
            "mode": booking.mode,
            "bookedBy": display_name(booking.user),
            "username": booking.user.get_username(),
            "clashesWith": lecture.activity,
            "classStart": lecture.start.isoformat(),
            "classEnd": lecture.end.isoformat(),
            "suggestedRoomId": alternative.id if alternative else None,
            "suggestedRoomName": alternative.name if alternative else None,
        })
    return result


@transaction.atomic
def activate(timetable, user, now=None, system=False):
    """
    Make `timetable` the active one. Refused while upcoming bookings clash with it.
    `system=True` is for the seed command (no signed-in user); the API always passes the faculty user.
    """
    if not system:
        require_staff(user)
    timetable = Timetable.objects.select_for_update().get(pk=timetable.pk)
    if timetable.status == Timetable.Status.ACTIVE:
        raise ValidationError({"status": "This timetable is already active."})
    clashes = conflicts(timetable, now)
    if clashes:
        raise ActivationBlocked({
            "detail": f"{len(clashes)} upcoming booking(s) clash with this timetable. Move or cancel them first.",
            "conflicts": len(clashes)})
    previous = capacity.active_timetable()
    if previous:
        previous.status = Timetable.Status.ARCHIVED
        previous.save(update_fields=["status"])
    timetable.status = Timetable.Status.ACTIVE
    timetable.activated_at = now or timezone.now()
    timetable.activated_by = user if user and user.pk else None
    try:
        timetable.save(update_fields=["status", "activated_at", "activated_by"])
    except IntegrityError:
        raise ActivationBlocked({"detail": "Another timetable was activated at the same moment. Try again."})
    TimetableEvent.objects.create(
        timetable=timetable, action=TimetableEvent.Action.ACTIVATED, actor=timetable.activated_by,
        detail=f"Replaced v{previous.version} {previous.name}" if previous else "First active timetable")
    return timetable


@transaction.atomic
def resolve(timetable, booking_id, action, user, room_id=None, now=None):
    """
    Faculty decision for one clashing booking: move it to another room that is free under both the
    active and the new timetable ("reassign"), or cancel it ("cancel"). Logged and shown to the student.
    """
    require_staff(user)
    now = now or timezone.now()
    booking = RoomBooking.objects.select_for_update().select_related("room", "user").filter(pk=booking_id).first()
    if booking is None:
        raise ValidationError({"bookingId": "No such booking."})
    if booking.status != RoomBooking.Status.ACTIVE or booking.end <= now:
        raise ValidationError({"bookingId": "Only active, upcoming bookings can be changed."})
    lecture = next((l for b, l in conflicts(timetable, now) if b.pk == booking.pk), None)
    if lecture is None:
        raise ValidationError({"bookingId": "This booking doesn't clash with that timetable."})
    reason = f"{booking.room_id} has {lecture.activity} then in timetable v{timetable.version}"

    if action == "cancel":
        from .services import cancel
        cancel(booking, user, note=f"Cancelled by {display_name(user)}: {reason}.")
        TimetableEvent.objects.create(timetable=timetable, booking=booking, actor=user,
                                      action=TimetableEvent.Action.BOOKING_CANCELLED,
                                      detail=f"{display_name(booking.user)}'s booking: {reason}")
        return booking
    if action != "reassign":
        raise ValidationError({"action": "Use reassign or cancel."})

    timetables = [t for t in (capacity.active_timetable(), timetable) if t is not None]
    if room_id:
        target = Classroom.objects.filter(pk=room_id).first()
        if target is None:
            raise ValidationError({"roomId": "Unknown room."})
        for option in timetables:
            seats = capacity.seats_for([target], booking.start, booking.end, timetable=option, exclude=booking)
            if not capacity.fits(seats[target.id], booking.attendees, booking.mode):
                raise ValidationError({"roomId": f"{target.name}: "
                                                 f"{capacity.why_not(seats[target.id], booking.attendees, booking.mode)}."})
    else:
        target = capacity.best_alternative(booking, timetables, now)
        if target is None:
            raise ValidationError({"roomId": "No other room fits this group then. Cancel the booking instead."})
    from .services import lock_room
    lock_room(target.id)
    old_room = booking.room_id
    booking.room = target
    booking.note = f"Moved from {old_room} to {target.id} by {display_name(user)}: {reason}."[:240]
    booking.save(update_fields=["room", "note"])
    TimetableEvent.objects.create(timetable=timetable, booking=booking, actor=user,
                                  action=TimetableEvent.Action.BOOKING_REASSIGNED,
                                  detail=f"{display_name(booking.user)}'s booking moved {old_room} → {target.id}: "
                                         f"{reason}"[:300])
    return booking


def schedule_json(timetable):
    return [{"weekday": e.weekday, "day": DAY_NAMES[e.weekday], "start": f"{e.start:%H:%M}",
             "end": f"{e.end:%H:%M}", "roomId": e.room_id, "activity": e.activity}
            for e in timetable.entries.all()]


def timetable_json(timetable, entries=False):
    data = {
        "id": timetable.id, "version": timetable.version, "name": timetable.name, "status": timetable.status,
        "sourceFilename": timetable.source_filename,
        "uploadedBy": display_name(timetable.uploaded_by) if timetable.uploaded_by else None,
        "createdAt": timetable.created_at.isoformat(),
        "activatedAt": timetable.activated_at.isoformat() if timetable.activated_at else None,
        "classCount": timetable.entries.count(),
    }
    if entries:
        data["entries"] = schedule_json(timetable)
    return data

