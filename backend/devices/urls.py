from django.urls import path

from .views import ScanView

urlpatterns = [
    path("devices/scan/", ScanView.as_view(), name="device-scan"),
]
