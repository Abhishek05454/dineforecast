from rest_framework.routers import DefaultRouter
from .views import DemandForecastViewSet, StaffingRequirementViewSet

router = DefaultRouter()
router.register("demand", DemandForecastViewSet, basename="demand-forecast")
router.register("staffing", StaffingRequirementViewSet, basename="staffing-requirement")

urlpatterns = router.urls
