from django.urls import path

from . import views

urlpatterns = [
    path("telemetry/", views.TelemetryView.as_view(), name="telemetry"),
    path("safelab/", views.dashboard, name="safelab-dashboard"),
    path("safelab/alerts/<int:pk>/acknowledge/", views.acknowledge, name="safelab-acknowledge"),
    path("safelab/labs/", views.fault_labs, name="safelab-fault-labs"),
    path("safelab/faults/", views.fault_reports, name="safelab-faults"),
    path("safelab/faults/analytics/", views.fault_analytics, name="safelab-fault-analytics"),
    path("safelab/faults/<int:pk>/<str:action>/", views.fault_decide, name="safelab-fault-decide"),
]
