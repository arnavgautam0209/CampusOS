from datetime import date, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.fields import DateTimeField
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from attendance.models import Classroom
from attendance.services import display_name

from . import services
from .models import RoomBooking
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
            } for b in busy],
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
        data = request.data if isinstance(request.data, dict) else {}
        start = DateTimeField().run_validation(data.get("start"))
        duration, attendees = data.get("durationMinutes", 60), data.get("attendees", 1)
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (duration, attendees)):
            raise ValidationError({"durationMinutes": "durationMinutes and attendees must be whole numbers."})
        booking = services.book_room(request.user, str(data.get("roomId", "")), start, duration,
                                     attendees=attendees, purpose=str(data.get("purpose") or ""))
        return Response(RoomBookingSerializer(booking).data, status=status.HTTP_201_CREATED)

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
