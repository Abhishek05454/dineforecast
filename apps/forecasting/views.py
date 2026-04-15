import logging

from rest_framework import filters, permissions, status, viewsets

logger = logging.getLogger(__name__)
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .models import DemandForecast, StaffingRequirement
from .serializers import (
    DemandForecastSerializer,
    ForecastQuerySerializer,
    ForecastResponseSerializer,
    StaffingRequirementSerializer,
)
from .services import (
    ForecastService,
    IngredientForecastService,
    StaffPlanningService,
    distribute_covers_by_hour,
)


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

        forecast_result = ForecastService(target_date=target_date).predict()
        total_covers = max(0, round(forecast_result.final_prediction))

        hourly_distribution = distribute_covers_by_hour(total_covers)
        hourly_breakdown = [
            {
                "hour": slot.hour,
                "covers": slot.covers,
                "share": round(slot.share, 4),
            }
            for slot in hourly_distribution.slots
        ]

        staff_plan_result = StaffPlanningService(
            covers_by_hour=hourly_distribution.as_dict()
        ).plan()
        staff_plan = [
            {
                "hour": hour_plan.hour,
                "covers": hour_plan.covers,
                "total_staff": hour_plan.total_staff(),
                "roles": [
                    {
                        "role": role.role,
                        "covers_per_staff": role.covers_per_staff,
                        "staff_required": role.staff_required,
                    }
                    for role in hour_plan.roles
                ],
            }
            for hour_plan in staff_plan_result.hours
        ]

        ingredient_plan = []
        ingredient_plan_available = True
        ingredient_plan_error = None
        try:
            ingredient_result = IngredientForecastService.from_database(
                predicted_covers=total_covers
            ).forecast()
            ingredient_plan = [
                {
                    "name": item.name,
                    "unit": item.unit,
                    "base_quantity": item.base_quantity,
                    "buffer_quantity": item.buffer_quantity,
                    "total_quantity": item.total_quantity,
                    "shelf_life_days": item.shelf_life_days,
                    "supplier_lead_time_days": item.supplier_lead_time_days,
                    "order_days_ahead": item.order_days_ahead,
                    "freshness_risk": item.freshness_risk,
                }
                for item in ingredient_result.requirements
            ]
        except ValueError as exc:
            ingredient_plan_available = False
            ingredient_plan_error = str(exc)
            logger.warning("Ingredient forecast unavailable for %s: %s", target_date, exc)

        payload = {
            "date": target_date,
            "total_covers": total_covers,
            "hourly_breakdown": hourly_breakdown,
            "staff_plan": staff_plan,
            "ingredient_plan": ingredient_plan,
            "ingredient_plan_available": ingredient_plan_available,
            "ingredient_plan_error": ingredient_plan_error,
        }
        response_serializer = ForecastResponseSerializer(payload)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
