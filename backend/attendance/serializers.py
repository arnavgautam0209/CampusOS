from rest_framework import serializers

from devices.models import Device, ScanEvent

from .models import AttendanceRecord, AttendanceSession, Classroom
from .services import display_name


# camelCase field names match the iOS Codable structs.
class SessionRecordSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()
    studentUsername = serializers.CharField(source="student.get_username", read_only=True)
    markedAt = serializers.DateTimeField(source="marked_at", read_only=True)
    deviceId = serializers.CharField(source="device_id", read_only=True, allow_null=True)

    class Meta:
        model = AttendanceRecord
        fields = ["id", "student", "studentUsername", "source", "markedAt", "deviceId"]

    def get_student(self, record):
        return display_name(record.student)


class LiveSessionSerializer(serializers.ModelSerializer):
    classroomId = serializers.CharField(source="classroom_id", read_only=True)
    classroomName = serializers.CharField(source="classroom.name", read_only=True)
    openedBy = serializers.SerializerMethodField()
    openedAt = serializers.DateTimeField(source="opened_at", read_only=True)
    closedAt = serializers.DateTimeField(source="closed_at", read_only=True)
    records = SessionRecordSerializer(many=True, read_only=True)

    class Meta:
        model = AttendanceSession
        fields = ["id", "title", "classroomId", "classroomName", "openedBy", "openedAt", "closedAt", "records"]

    def get_openedBy(self, session):
        return display_name(session.opened_by) if session.opened_by else None


class ClassroomSerializer(serializers.ModelSerializer):
    hasOpenSession = serializers.SerializerMethodField()

    class Meta:
        model = Classroom
        fields = ["id", "name", "hasOpenSession"]

    def get_hasOpenSession(self, classroom):
        return classroom.id in self.context["open_classroom_ids"]


class ScanSerializer(serializers.ModelSerializer):
    deviceId = serializers.CharField(source="device_id", read_only=True)
    classroomId = serializers.CharField(source="classroom_id_sent", read_only=True)
    student = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = ScanEvent
        fields = ["id", "deviceId", "uid", "result", "reason", "student", "classroomId", "createdAt"]

    def get_student(self, scan):
        return display_name(scan.student) if scan.student else None


class ReaderSerializer(serializers.ModelSerializer):
    classroomId = serializers.CharField(source="classroom_id", read_only=True, allow_null=True)
    labId = serializers.CharField(source="lab_id", read_only=True, allow_null=True)
    isActive = serializers.BooleanField(source="is_active", read_only=True)
    hasKey = serializers.SerializerMethodField()
    lastSeenAt = serializers.DateTimeField(source="last_seen_at", read_only=True)

    class Meta:
        model = Device
        fields = ["id", "name", "classroomId", "labId", "isActive", "hasKey", "lastSeenAt"]

    def get_hasKey(self, device):
        return bool(device.key_hash)


class MyAttendanceSerializer(serializers.ModelSerializer):
    sessionId = serializers.IntegerField(source="session_id", read_only=True)
    session = serializers.CharField(source="session.title", read_only=True)
    classroomId = serializers.CharField(source="session.classroom_id", read_only=True)
    classroomName = serializers.CharField(source="session.classroom.name", read_only=True)
    markedAt = serializers.DateTimeField(source="marked_at", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = ["id", "sessionId", "session", "classroomId", "classroomName", "source", "markedAt"]
