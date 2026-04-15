from rest_framework import serializers
from .models import DemandForecast, StaffingRequirement


class StaffingRequirementSerializer(serializers.ModelSerializer):
    total_staff = serializers.SerializerMethodField()

    class Meta:
        model = StaffingRequirement
        fields = [
            "id", "front_of_house", "back_of_house", "management",
            "total_staff", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_total_staff(self, obj):
        return obj.total_staff()


class DemandForecastSerializer(serializers.ModelSerializer):
    staffing = StaffingRequirementSerializer(read_only=True)

    class Meta:
        model = DemandForecast
        fields = [
            "id", "forecast_date", "meal_period", "expected_covers",
            "confidence_score", "notes", "staffing", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ForecastQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=True)


class HourlyBreakdownItemSerializer(serializers.Serializer):
    hour = serializers.IntegerField(min_value=0, max_value=23)
    covers = serializers.IntegerField(min_value=0)
    share = serializers.FloatField(min_value=0)


class StaffRolePlanItemSerializer(serializers.Serializer):
    role = serializers.CharField()
    covers_per_staff = serializers.IntegerField(min_value=1)
    staff_required = serializers.IntegerField(min_value=0)


class StaffPlanHourItemSerializer(serializers.Serializer):
    hour = serializers.IntegerField(min_value=0, max_value=23)
    covers = serializers.IntegerField(min_value=0)
    total_staff = serializers.IntegerField(min_value=0)
    roles = StaffRolePlanItemSerializer(many=True)


class IngredientPlanItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    unit = serializers.CharField()
    base_quantity = serializers.FloatField(min_value=0)
    buffer_quantity = serializers.FloatField(min_value=0)
    total_quantity = serializers.FloatField(min_value=0)
    shelf_life_days = serializers.IntegerField(min_value=0)
    supplier_lead_time_days = serializers.IntegerField(min_value=0)
    order_days_ahead = serializers.IntegerField(min_value=0)
    freshness_risk = serializers.BooleanField()


class ForecastResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    total_covers = serializers.IntegerField(min_value=0)
    hourly_breakdown = HourlyBreakdownItemSerializer(many=True)
    staff_plan = StaffPlanHourItemSerializer(many=True)
    ingredient_plan = IngredientPlanItemSerializer(many=True)
    ingredient_plan_available = serializers.BooleanField()
    ingredient_plan_error = serializers.CharField(allow_null=True)
