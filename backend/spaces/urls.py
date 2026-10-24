from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("spaces/bookings", views.RoomBookingViewSet, basename="room-booking")

urlpatterns = [
    path("spaces/", views.availability, name="spaces"),
    path("spaces/utilization/", views.utilization, name="spaces-utilization"),
] + router.urls
