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
