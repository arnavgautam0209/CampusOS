from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import Booking
from .serializers import BookingCreateSerializer, BookingSerializer


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /bookings/                    your bookings and requests
    GET  /bookings/?scope=pending      staff: requests waiting for approval (soonest first)
    GET  /bookings/?scope=all          staff: every booking
    POST /bookings/                    {labID, start, durationMinutes, purpose}
    GET  /bookings/{id}/
    POST /bookings/{id}/cancel/        cancel a booking or withdraw a request
    POST /bookings/{id}/approve/       staff, {note}
    POST /bookings/{id}/decline/       staff, {note}
    """

    serializer_class = BookingSerializer

    def get_queryset(self):
        services.expire_stale_requests()
        bookings = Booking.objects.select_related("lab", "user", "decided_by")
        staff = self.request.user.is_staff
        if self.action == "list":
            scope = self.request.query_params.get("scope")
            if staff and scope == "pending":
                return bookings.filter(status=Booking.Status.PENDING).order_by("start")
            if staff and scope == "all":
                return bookings
            return bookings.filter(user=self.request.user)
        # Single-booking actions: staff may act on any booking, others only on their own (404 otherwise).
        return bookings if staff else bookings.filter(user=self.request.user)

    def create(self, request):
        payload = BookingCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        booking = services.create_booking(
            user=request.user,
            lab_id=payload.validated_data["labID"],
            start=payload.validated_data["start"],
            duration_minutes=payload.validated_data["durationMinutes"],
            purpose=payload.validated_data["purpose"],
        )
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = services.cancel_booking(self.get_object())
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        booking = services.approve_booking(self.get_object(), request.user, note=self._note(request))
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        booking = services.decline_booking(self.get_object(), request.user, note=self._note(request))
        return Response(BookingSerializer(booking).data)

    @staticmethod
    def _note(request):
        return str(request.data.get("note", "")) if isinstance(request.data, dict) else ""
