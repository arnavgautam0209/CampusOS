from rest_framework import serializers

from .models import Booking


# Output matches the iOS LabBooking struct.
class BookingSerializer(serializers.ModelSerializer):
    labID = serializers.CharField(source="lab_id", read_only=True)
    labName = serializers.CharField(source="lab.name", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    checkedInAt = serializers.DateTimeField(source="checked_in_at", read_only=True)
    student = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.get_username", read_only=True)
    decidedBy = serializers.SerializerMethodField()
    decidedAt = serializers.DateTimeField(source="decided_at", read_only=True)
    decisionNote = serializers.CharField(source="decision_note", read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "labID", "labName", "start", "end", "status", "purpose", "createdAt", "checkedInAt",
                  "student", "username", "decidedBy", "decidedAt", "decisionNote"]
        read_only_fields = fields

    def get_student(self, booking):
        return booking.user.get_full_name() or booking.user.get_username()

    def get_decidedBy(self, booking):
        if not booking.decided_by:
            return None
        return booking.decided_by.get_full_name() or booking.decided_by.get_username()


class BookingCreateSerializer(serializers.Serializer):
    labID = serializers.CharField(max_length=32)
    start = serializers.DateTimeField()
    durationMinutes = serializers.IntegerField(default=60)
    purpose = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
