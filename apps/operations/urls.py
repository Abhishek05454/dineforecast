from rest_framework.routers import DefaultRouter
from .views import ShiftViewSet, InventoryItemViewSet

router = DefaultRouter()
router.register("shifts", ShiftViewSet, basename="shift")
router.register("inventory", InventoryItemViewSet, basename="inventory")

urlpatterns = router.urls
