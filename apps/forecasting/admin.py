from django.contrib import admin
from .models import DemandForecast, StaffingRequirement


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ["forecast_date", "meal_period", "expected_covers", "confidence_score"]
    list_filter = ["meal_period", "forecast_date"]
    search_fields = ["notes"]


@admin.register(StaffingRequirement)
class StaffingRequirementAdmin(admin.ModelAdmin):
    list_display = ["forecast", "front_of_house", "back_of_house", "management"]
