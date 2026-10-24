from rest_framework import serializers

from .models import Certification, UserCertification


class CertificationSerializer(serializers.ModelSerializer):
    validityDays = serializers.IntegerField(source="validity_days", read_only=True)

    class Meta:
        model = Certification
        fields = ["id", "name", "description", "validityDays"]


class UserCertificationSerializer(serializers.ModelSerializer):
    certification = CertificationSerializer(read_only=True)
    username = serializers.CharField(source="user.get_username", read_only=True)
    studentName = serializers.SerializerMethodField()
    requestedAt = serializers.DateTimeField(source="requested_at", read_only=True)
    approvedBy = serializers.SerializerMethodField()
    approvedAt = serializers.DateTimeField(source="approved_at", read_only=True)
    expiresAt = serializers.DateTimeField(source="expires_at", read_only=True)
    isValid = serializers.BooleanField(source="is_valid", read_only=True)

    class Meta:
        model = UserCertification
        fields = ["id", "username", "studentName", "certification", "status", "isValid",
                  "requestedAt", "approvedBy", "approvedAt", "expiresAt"]

    def get_studentName(self, record):
        return record.user.get_full_name() or record.user.get_username()

    def get_approvedBy(self, record):
        return record.approved_by.get_username() if record.approved_by else None
