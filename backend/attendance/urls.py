from django.urls import path

from . import views

urlpatterns = [
    path("attendance/live/", views.live, name="attendance-live"),
    path("attendance/mine/", views.mine, name="attendance-mine"),
    path("attendance/sessions/", views.open_session, name="attendance-session-open"),
    path("attendance/sessions/<int:pk>/close/", views.close_session, name="attendance-session-close"),
    path("attendance/sessions/<int:pk>/report/", views.session_report, name="attendance-session-report"),
    path("attendance/sessions/<int:pk>/report/pdf/", views.session_report_pdf, name="attendance-session-report-pdf"),
    path("attendance/sessions/<int:pk>/report/csv/", views.session_report_csv, name="attendance-session-report-csv"),
]
