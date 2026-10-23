from django.urls import path

from . import views

urlpatterns = [
    path("attendance/live/", views.live, name="attendance-live"),
    path("attendance/mine/", views.mine, name="attendance-mine"),
]
