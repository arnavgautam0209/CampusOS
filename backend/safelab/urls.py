from django.urls import path

from . import views

urlpatterns = [
    path("telemetry/", views.TelemetryView.as_view(), name="telemetry"),
    path("safelab/", views.dashboard, name="safelab-dashboard"),
    path("safelab/alerts/<int:pk>/acknowledge/", views.acknowledge, name="safelab-acknowledge"),
]
