from rest_framework import serializers

from attendance.services import display_name

from .models import RoomBooking


class RoomBookingSerializer(serializers.ModelSerializer):
    roomId = serializers.CharField(source="room_id", read_only=True)
    roomName = serializers.CharField(source="room.name", read_only=True)
    bookedBy = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.get_username", read_only=True)
    roomCapacity = serializers.IntegerField(source="room.capacity", read_only=True)
    checkedInAt = serializers.DateTimeField(source="checked_in_at", read_only=True)

    class Meta:
        model = RoomBooking
        fields = ["id", "roomId", "roomName", "roomCapacity", "start", "end", "purpose", "attendees", "mode",
                  "status", "note", "checkedInAt", "bookedBy", "username"]
        read_only_fields = fields

    def get_bookedBy(self, booking):
        return display_name(booking.user)
