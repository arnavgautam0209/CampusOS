from django.db.models import Count, Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from devices.models import Device, ScanEvent

from . import reports, services
from .models import AttendanceRecord, AttendanceSession, Classroom
from .serializers import (ClassroomSerializer, LiveSessionSerializer, MyAttendanceSerializer, ReaderSerializer,
                          ScanSerializer, SessionSummarySerializer)

RECENT_SCAN_LIMIT = 25
SESSION_LIST_LIMIT = 50


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


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def open_session(request):
    """
    GET  faculty: recent sessions, open and closed, newest first (?classroom=ECE to filter).
    POST faculty: {"classroomId": "ROOM-101", "title": "CS201 Lecture 5"} → 201, or 409 if one is already open.
    """
    if request.method == "GET":
        sessions = AttendanceSession.objects.select_related("classroom", "opened_by").annotate(
            present_count=Count("records")).order_by("-opened_at", "-id")   # GROUP BY drops Meta.ordering
        if request.query_params.get("classroom"):
            sessions = sessions.filter(classroom__id__iexact=request.query_params["classroom"])
        return Response(SessionSummarySerializer(sessions[:SESSION_LIST_LIMIT], many=True).data)
    session = services.open_session(request.data.get("classroomId"), request.data.get("title"), request.user)
    return Response(LiveSessionSerializer(session).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def close_session(request, pk):
    """Faculty: stops readers in that room from marking attendance."""
    session = services.close_session(get_object_or_404(AttendanceSession, pk=pk), request.user)
    return Response(LiveSessionSerializer(session).data)


def _report_for(pk):
    session = get_object_or_404(AttendanceSession.objects.select_related("classroom", "opened_by"), pk=pk)
    return reports.build_report(session)


def _download(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


@api_view(["GET"])
@permission_classes([IsAdminUser])
def session_report(request, pk):
    """Faculty: who was present and absent in one session. Provisional while the session is open."""
    return Response(reports.report_json(_report_for(pk)))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def session_report_pdf(request, pk):
    report = _report_for(pk)
    return _download(reports.report_pdf(report), "application/pdf", f"{report.filename_stem}.pdf")


@api_view(["GET"])
@permission_classes([IsAdminUser])
def session_report_csv(request, pk):
    report = _report_for(pk)
    return _download(reports.report_csv(report), "text/csv; charset=utf-8", f"{report.filename_stem}.csv")
