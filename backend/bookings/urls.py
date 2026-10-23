from rest_framework.routers import DefaultRouter

from .views import BookingViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = router.urls
