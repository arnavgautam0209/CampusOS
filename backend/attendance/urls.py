from django.urls import path

from . import views

urlpatterns = [
    path("attendance/live/", views.live, name="attendance-live"),
    path("attendance/mine/", views.mine, name="attendance-mine"),
    path("attendance/sessions/", views.open_session, name="attendance-session-open"),
    path("attendance/sessions/<int:pk>/close/", views.close_session, name="attendance-session-close"),
]
