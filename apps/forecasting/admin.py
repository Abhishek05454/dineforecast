from django.contrib import admin
from .models import DemandForecast, StaffingRequirement, HistoricalCover, StaffRole, DishPopularity


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ["forecast_date", "meal_period", "expected_covers", "confidence_score"]
    list_filter = ["meal_period", "forecast_date"]
    search_fields = ["notes"]


@admin.register(StaffingRequirement)
class StaffingRequirementAdmin(admin.ModelAdmin):
    list_display = ["forecast", "front_of_house", "back_of_house", "management"]


@admin.register(HistoricalCover)
class HistoricalCoverAdmin(admin.ModelAdmin):
    list_display = ["date", "hour", "covers", "weather", "is_weekend", "special_event"]
    list_filter = ["is_weekend", "weather"]
    search_fields = ["special_event"]


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ["role", "covers_per_staff"]


@admin.register(DishPopularity)
class DishPopularityAdmin(admin.ModelAdmin):
    list_display = ["dish_name", "average_orders_percentage"]
    search_fields = ["dish_name"]
