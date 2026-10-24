from datetime import date, datetime, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.fields import DateTimeField
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from attendance.models import Classroom
from attendance.services import display_name

from . import capacity, services, timetables
from .models import RoomBooking, Timetable, TimetableEvent
from .serializers import RoomBookingSerializer


def _parse_day(raw):
    today = timezone.localdate()
    if not raw:
        return today
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        raise ValidationError({"date": "Use YYYY-MM-DD."})
    if not (today <= day <= today + timedelta(days=30)):
        raise ValidationError({"date": "Pick a date from today up to 30 days ahead."})
    return day


@api_view(["GET"])
def availability(request):
    """
    GET /api/v1/spaces/?date=YYYY-MM-DD (default today): every room with its busy slots
    between 08:00 and 20:00. Students only see whether a slot is theirs; staff see who booked.
    """
    now = timezone.now()
    services.release_no_shows(now)
    day = _parse_day(request.query_params.get("date"))
    day_start, day_end = services.day_bounds(day)
    in_class = services.rooms_in_class_now() if day == timezone.localdate() else set()
    staff = request.user.is_staff

    bookings = {}
    for booking in (RoomBooking.objects.filter(status=RoomBooking.Status.ACTIVE, start__lt=day_end,
                                               end__gt=day_start).select_related("user").order_by("start")):
        bookings.setdefault(booking.room_id, []).append(booking)
    lectures = {}
    for lecture in capacity.lectures_between(day_start, day_end):
        lectures.setdefault(lecture.room_id, []).append(lecture)

    rooms = []
    for room in Classroom.objects.order_by("kind", "id"):
        busy = bookings.get(room.id, [])
        booked_now = any(b.start <= now < b.end for b in busy)
        rooms.append({
            "id": room.id,
            "name": room.name,
            "kind": room.kind,
            "capacity": room.capacity,
            "location": room.location,
            "features": [f.strip() for f in room.features.split(",") if f.strip()],
            "isBookable": room.is_bookable or staff,
            "inClassNow": room.id in in_class,
            "freeNow": day == timezone.localdate() and not booked_now and room.id not in in_class,
            "busy": [{
                "start": b.start.isoformat(),
                "end": b.end.isoformat(),
                "mine": b.user_id == request.user.pk,
                "bookedBy": display_name(b.user) if staff else None,
                "checkedIn": b.checked_in_at is not None,
                "mode": b.mode,
                "attendees": b.attendees,
            } for b in busy],
            # Classes from the active timetable: the whole room is taken.
            "lectures": [{"start": l.start.isoformat(), "end": l.end.isoformat(), "activity": l.activity}
                         for l in lectures.get(room.id, [])],
        })
    return Response({"date": day.isoformat(), "dayStart": day_start.isoformat(), "dayEnd": day_end.isoformat(),
                     "rooms": rooms})


class RoomBookingViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET  /spaces/bookings/              your bookings from the last day onwards
    GET  /spaces/bookings/?scope=all    staff: all active upcoming bookings
    POST /spaces/bookings/              {roomId, start, durationMinutes, attendees, purpose}
    POST /spaces/bookings/{id}/cancel/
    POST /spaces/bookings/{id}/check-in/
    """

    serializer_class = RoomBookingSerializer

    def get_queryset(self):
        services.release_no_shows()
        bookings = RoomBooking.objects.select_related("room", "user")
        if self.action == "list":
            if self.request.user.is_staff and self.request.query_params.get("scope") == "all":
                return bookings.filter(status=RoomBooking.Status.ACTIVE, end__gt=timezone.now())
            return bookings.filter(user=self.request.user, end__gt=timezone.now() - timedelta(days=1))
        if self.request.user.is_staff:
            return bookings
        return bookings.filter(user=self.request.user)

    def create(self, request):
        """{roomId, start, durationMinutes, attendees, purpose, mode}: mode is "shared" or "exclusive" (default)."""
        data = request.data if isinstance(request.data, dict) else {}
        start = DateTimeField().run_validation(data.get("start"))
        duration, attendees = data.get("durationMinutes", 60), data.get("attendees", 1)
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (duration, attendees)):
            raise ValidationError({"durationMinutes": "durationMinutes and attendees must be whole numbers."})
        booking = services.book_room(request.user, str(data.get("roomId", "")), start, duration,
                                     attendees=attendees, purpose=str(data.get("purpose") or ""),
                                     mode=services.parse_mode(data.get("mode")))
        return Response(RoomBookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """Same as the default list: your bookings from the last day onwards."""
        bookings = RoomBooking.objects.select_related("room", "user").filter(
            user=request.user, end__gt=timezone.now() - timedelta(days=1))
        return Response(RoomBookingSerializer(bookings, many=True).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(RoomBookingSerializer(services.cancel(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        return Response(RoomBookingSerializer(services.check_in(self.get_object(), request.user)).data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def utilization(request):
    """GET /api/v1/spaces/utilization/?days=7 : staff room usage summary."""
    try:
        days = max(1, min(30, int(request.query_params.get("days", 7))))
    except ValueError:
        raise ValidationError({"days": "Use a number of days from 1 to 30."})
    return Response({"days": days, "rooms": services.utilization(days)})


def _int_param(params, name, default):
    raw = params.get(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: "Use a whole number."})


def _room_json(seats, group_size, mode):
    available = seats.room.capacity if mode == RoomBooking.Mode.EXCLUSIVE and not seats.bookings else seats.free
    return {
        "id": seats.room.id, "name": seats.room.name, "kind": seats.room.kind, "location": seats.room.location,
        "capacity": seats.room.capacity,
        "availableSeats": available,
        "bookedSeats": seats.peak_booked,
        "seatsAfterBooking": max(0, available - group_size),
        "reason": None,
    }


@api_view(["GET"])
def recommend(request):
    """
    GET /api/v1/spaces/availability/?date=YYYY-MM-DD&start=11:00&duration=60&group_size=8&mode=shared
    Rooms that fit the group for the whole time, best fit first, using free seats at that time.
    `kind` = classroom (default), study_room, meeting_room or all.
    """
    params = request.query_params
    day = _parse_day(params.get("date"))
    try:
        start_time = datetime.strptime(params.get("start", ""), "%H:%M").time()
    except ValueError:
        raise ValidationError({"start": "Use HH:MM, e.g. 11:00."})
    start = timezone.make_aware(datetime.combine(day, start_time))
    duration = _int_param(params, "duration", 60)
    group_size = _int_param(params, "group_size", 1)
    mode = services.parse_mode(params.get("mode"), default=RoomBooking.Mode.SHARED)
    kind = params.get("kind", "classroom")
    result = services.recommend(request.user, start, duration, group_size, mode, kind)

    rooms = [_room_json(s, group_size, mode) for s in result["eligible"]]
    unavailable = []
    for seats in result["unavailable"]:
        row = _room_json(seats, group_size, mode)
        row["reason"] = capacity.why_not(seats, group_size, mode)
        unavailable.append(row)
    best = rooms[0] if rooms else None
    people = f"{group_size} {'person' if group_size == 1 else 'people'}"
    if best:
        message = (f"Best fit for {people} — {best['seatsAfterBooking']} seat"
                   f"{'' if best['seatsAfterBooking'] == 1 else 's'} would remain available.")
    elif not unavailable:
        message = "No rooms of that kind are set up yet."
    else:
        message = (f"No room has {group_size} seats free for the whole of "
                   f"{timezone.localtime(result['start']):%H:%M}–{timezone.localtime(result['end']):%H:%M}. "
                   "Try a smaller group, a shorter time or another start time.")
    active = result["timetable"]
    return Response({
        "date": day.isoformat(),
        "start": result["start"].isoformat(), "end": result["end"].isoformat(),
        "groupSize": group_size, "mode": mode,
        "timetable": {"id": active.id, "version": active.version, "name": active.name} if active else None,
        "recommended": best, "rooms": rooms, "unavailable": unavailable, "message": message,
    })


class TimetableViewSet(viewsets.GenericViewSet):
    """
    GET  /spaces/timetables/                    faculty: every version, newest first
    GET  /spaces/timetables/active/             anyone signed in: the active timetable with its classes
    GET  /spaces/timetables/{id}/               faculty: one version with its classes
    POST /spaces/timetables/upload/             faculty: {name, filename, csv} (or multipart "file") → draft
    GET  /spaces/timetables/{id}/preview/       faculty: rooms that become occupied/free vs the active one
    GET  /spaces/timetables/{id}/conflicts/     faculty: upcoming bookings that clash, with a suggested room
    POST /spaces/timetables/{id}/resolve/       faculty: {bookingId, action: reassign|cancel, roomId?}
    POST /spaces/timetables/{id}/activate/      faculty: replace the active timetable (409 while conflicts)
    GET  /spaces/timetables/history/            faculty: audit log
    """

    queryset = Timetable.objects.all()

    def get_permissions(self):
        # Students may read the active timetable; everything else is faculty-only.
        return [IsAuthenticated()] if self.action == "active" else [IsAdminUser()]

    def list(self, request):
        return Response([timetables.timetable_json(t) for t in Timetable.objects.all()])

    def retrieve(self, request, pk=None):
        return Response(timetables.timetable_json(self.get_object(), entries=True))

    @action(detail=False, methods=["get"])
    def active(self, request):
        timetable = capacity.active_timetable()
        if timetable is None:
            return Response({"detail": "No timetable is active."}, status=status.HTTP_404_NOT_FOUND)
        return Response(timetables.timetable_json(timetable, entries=True))

    @action(detail=False, methods=["post"])
    def upload(self, request):
        upload = request.FILES.get("file")
        if upload is not None:
            try:
                text = upload.read(timetables.MAX_BYTES + 1).decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValidationError({"detail": "The file must be UTF-8 text (CSV).", "errors": []})
            filename = upload.name
        else:
            text = request.data.get("csv") if isinstance(request.data, dict) else None
            if not isinstance(text, str):
                raise ValidationError({"detail": "Send the CSV text as \"csv\" or a file as \"file\".",
                                       "errors": []})
            filename = str(request.data.get("filename") or "")
        timetable = timetables.upload(request.user, request.data.get("name"), text, filename)
        body = timetables.timetable_json(timetable, entries=True)
        body["preview"] = self._preview(timetable)
        body["conflicts"] = timetables.conflict_json(timetable)
        return Response(body, status=status.HTTP_201_CREATED)

    @staticmethod
    def _preview(timetable):
        result = timetables.preview(timetable)
        against = result["against"]
        return {"againstVersion": against.version if against else None,
                "againstName": against.name if against else None, "changes": result["changes"]}

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        return Response(self._preview(self.get_object()))

    @action(detail=True, methods=["get"])
    def conflicts(self, request, pk=None):
        return Response(timetables.conflict_json(self.get_object()))

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        data = request.data if isinstance(request.data, dict) else {}
        booking = timetables.resolve(self.get_object(), data.get("bookingId"), data.get("action"), request.user,
                                     room_id=data.get("roomId") or None)
        return Response(RoomBookingSerializer(booking).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        timetable = timetables.activate(self.get_object(), request.user)
        return Response(timetables.timetable_json(timetable))

    @action(detail=False, methods=["get"])
    def history(self, request):
        events = TimetableEvent.objects.select_related("timetable", "actor")[:100]
        return Response([{
            "action": e.action, "detail": e.detail, "createdAt": e.created_at.isoformat(),
            "timetableVersion": e.timetable.version if e.timetable else None,
            "actor": display_name(e.actor) if e.actor else None,
        } for e in events])
