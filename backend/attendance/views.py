from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from devices.models import Device, ScanEvent

from . import services
from .models import AttendanceRecord, AttendanceSession, Classroom
from .serializers import (ClassroomSerializer, LiveSessionSerializer, MyAttendanceSerializer, ReaderSerializer,
                          ScanSerializer)

RECENT_SCAN_LIMIT = 25


@api_view(["GET"])
@permission_classes([IsAdminUser])
def live(request):
    """
    Faculty dashboard, polled by the app every few seconds:
    open sessions with who's present, readers, and the latest scans (newest first).
    """
    records = AttendanceRecord.objects.select_related("student").order_by("marked_at")
    sessions = (
        AttendanceSession.objects.filter(closed_at__isnull=True)
        .select_related("classroom", "opened_by")
        .prefetch_related(Prefetch("records", queryset=records))
        .order_by("classroom_id")
    )
    scans = ScanEvent.objects.select_related("student").order_by("-created_at", "-id")[:RECENT_SCAN_LIMIT]
    open_ids = {session.classroom_id for session in sessions}
    return Response({
        "generatedAt": timezone.now().isoformat(),
        "openSessions": LiveSessionSerializer(sessions, many=True).data,
        "classrooms": ClassroomSerializer(Classroom.objects.all(), many=True,
                                          context={"open_classroom_ids": open_ids}).data,
        "readers": ReaderSerializer(Device.objects.all(), many=True).data,
        "recentScans": ScanSerializer(scans, many=True).data,
    })


@api_view(["GET"])
def mine(request):
    """The signed-in student's attendance, newest first."""
    records = (
        AttendanceRecord.objects.filter(student=request.user)
        .select_related("session", "session__classroom")
        .order_by("-marked_at")
    )
    return Response(MyAttendanceSerializer(records, many=True).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def open_session(request):
    """Faculty: {"classroomId": "ROOM-101", "title": "CS201 Lecture 5"} → 201, or 409 if one is already open."""
    session = services.open_session(request.data.get("classroomId"), request.data.get("title"), request.user)
    return Response(LiveSessionSerializer(session).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def close_session(request, pk):
    """Faculty: stops readers in that room from marking attendance."""
    session = services.close_session(get_object_or_404(AttendanceSession, pk=pk), request.user)
    return Response(LiveSessionSerializer(session).data)
