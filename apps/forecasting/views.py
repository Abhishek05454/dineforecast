import logging

from django.conf import settings
from django.core.cache import cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DemandForecast, StaffingRequirement
from .serializers import (
    DemandForecastSerializer,
    ForecastQuerySerializer,
    StaffingRequirementSerializer,
)
from .tasks import _build_forecast_payload, _forecast_cache_key

logger = logging.getLogger(__name__)


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


class ForecastAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query_serializer = ForecastQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        target_date = query_serializer.validated_data["date"]

        cache_key = _forecast_cache_key(target_date)
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Forecast cache hit for %s", target_date)
            return Response(cached, status=status.HTTP_200_OK)

        logger.debug("Forecast cache miss for %s", target_date)
        serialized = _build_forecast_payload(target_date)
        cache.set(cache_key, serialized, timeout=getattr(settings, "FORECAST_CACHE_TTL", 60 * 60 * 6))
        return Response(serialized, status=status.HTTP_200_OK)
