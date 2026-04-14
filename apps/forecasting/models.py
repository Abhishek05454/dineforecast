from django.db import models
from core.models import BaseModel


class DemandForecast(BaseModel):
    class MealPeriod(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        LUNCH = "lunch", "Lunch"
        DINNER = "dinner", "Dinner"

    forecast_date = models.DateField()
    meal_period = models.CharField(max_length=20, choices=MealPeriod.choices)
    expected_covers = models.PositiveIntegerField()
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("forecast_date", "meal_period")
        ordering = ["-forecast_date", "meal_period"]

    def __str__(self):
        return f"{self.forecast_date} | {self.meal_period} | {self.expected_covers} covers"


class StaffingRequirement(BaseModel):
    forecast = models.OneToOneField(
        DemandForecast, on_delete=models.CASCADE, related_name="staffing"
    )
    front_of_house = models.PositiveIntegerField()
    back_of_house = models.PositiveIntegerField()
    management = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]

    def total_staff(self):
        return self.front_of_house + self.back_of_house + self.management

    def __str__(self):
        return f"Staffing for {self.forecast}"
