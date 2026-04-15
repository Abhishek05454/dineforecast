from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import DemandForecastViewSet, ForecastAPIView, StaffingRequirementViewSet

router = DefaultRouter()
router.register("demand", DemandForecastViewSet, basename="demand-forecast")
router.register("staffing", StaffingRequirementViewSet, basename="staffing-requirement")

urlpatterns = router.urls + [
    path("forecast/", ForecastAPIView.as_view(), name="forecast-summary"),
]
