from rest_framework.routers import DefaultRouter

from .views import InventoryViewSet, LoanViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
# Register loans first so "inventory/loans/" isn't read as an equipment id.
router.register("inventory/loans", LoanViewSet, basename="loan")
router.register("inventory", InventoryViewSet, basename="inventory")

urlpatterns = router.urls
