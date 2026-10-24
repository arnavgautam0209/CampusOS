from django.contrib import admin
from django.urls import include, path

from devices.simple_scan import SimpleScanView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok", "service": "campusos", "apiVersion": "v1"})


api_v1 = [
    path("health/", health, name="health"),
    path("", include("accounts.urls")),
    path("", include("labs.urls")),
    path("", include("bookings.urls")),
    path("", include("skillpass.urls")),
    path("", include("devices.urls")),
    path("", include("attendance.urls")),
    path("", include("planner.urls")),
    path("", include("inventory.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    # AttendX ESP32 firmware contract (firmware/README.md); same rules as /api/v1/devices/scan/.
    path("api/scan/", SimpleScanView.as_view(), name="simple-scan"),
]
