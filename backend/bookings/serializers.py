from rest_framework import serializers

from .models import Booking


# Output matches the iOS LabBooking struct (id, labID, labName, start, end, status, checkedInAt).
class BookingSerializer(serializers.ModelSerializer):
    labID = serializers.CharField(source="lab_id", read_only=True)
    labName = serializers.CharField(source="lab.name", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    checkedInAt = serializers.DateTimeField(source="checked_in_at", read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "labID", "labName", "start", "end", "status", "createdAt", "checkedInAt"]
        read_only_fields = fields


class BookingCreateSerializer(serializers.Serializer):
    labID = serializers.CharField(max_length=32)
    start = serializers.DateTimeField()
    durationMinutes = serializers.IntegerField(default=60)
