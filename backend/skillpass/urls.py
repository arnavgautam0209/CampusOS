from rest_framework.routers import DefaultRouter

from .views import CertificationRecordViewSet, CertificationViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("certifications", CertificationViewSet, basename="certification")
router.register("certification-records", CertificationRecordViewSet, basename="certification-record")

urlpatterns = router.urls
