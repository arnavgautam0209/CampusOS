from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import Booking
from .serializers import BookingCreateSerializer, BookingSerializer


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /bookings/              your bookings (staff see all)
    POST /bookings/              {labID, start, durationMinutes}
    GET  /bookings/{id}/
    POST /bookings/{id}/cancel/
    """

    serializer_class = BookingSerializer

    def get_queryset(self):
        bookings = Booking.objects.select_related("lab")
        if self.request.user.is_staff:
            return bookings
        return bookings.filter(user=self.request.user)

    def create(self, request):
        payload = BookingCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        booking = services.create_booking(
            user=request.user,
            lab_id=payload.validated_data["labID"],
            start=payload.validated_data["start"],
            duration_minutes=payload.validated_data["durationMinutes"],
        )
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        # get_object() is scoped to the caller's bookings, so other users get 404.
        booking = services.cancel_booking(self.get_object())
        return Response(BookingSerializer(booking).data)
