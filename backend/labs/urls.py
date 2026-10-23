from rest_framework.routers import DefaultRouter

from .views import LabViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("labs", LabViewSet, basename="lab")

urlpatterns = router.urls
