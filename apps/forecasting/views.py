from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import DemandForecast, StaffingRequirement
from .serializers import DemandForecastSerializer, StaffingRequirementSerializer


class DemandForecastViewSet(viewsets.ModelViewSet):
    queryset = DemandForecast.objects.select_related("staffing").all()
    serializer_class = DemandForecastSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["forecast_date", "meal_period"]
    ordering_fields = ["forecast_date", "expected_covers"]


class StaffingRequirementViewSet(viewsets.ModelViewSet):
    queryset = StaffingRequirement.objects.select_related("forecast").all()
    serializer_class = StaffingRequirementSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["forecast__forecast_date", "forecast__meal_period"]
