from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from devices.models import Device, ScanEvent

from .models import AttendanceRecord, AttendanceSession
from .serializers import LiveSessionSerializer, MyAttendanceSerializer, ReaderSerializer, ScanSerializer

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
    return Response({
        "generatedAt": timezone.now().isoformat(),
        "openSessions": LiveSessionSerializer(sessions, many=True).data,
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
