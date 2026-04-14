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


class HistoricalCover(BaseModel):
    class Weather(models.TextChoices):
        SUNNY = "sunny", "Sunny"
        CLOUDY = "cloudy", "Cloudy"
        RAINY = "rainy", "Rainy"
        SNOWY = "snowy", "Snowy"

    date = models.DateField()
    hour = models.PositiveSmallIntegerField()
    covers = models.PositiveIntegerField()
    weather = models.CharField(max_length=20, choices=Weather.choices, blank=True)
    is_weekend = models.BooleanField(default=False)
    special_event = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("date", "hour")
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["is_weekend"]),
        ]
        ordering = ["-date", "hour"]

    def __str__(self):
        return f"{self.date} {self.hour:02d}:00 — {self.covers} covers"


class StaffRole(BaseModel):
    class Role(models.TextChoices):
        WAITER = "waiter", "Waiter"
        CHEF = "chef", "Chef"
        BARTENDER = "bartender", "Bartender"
        MANAGER = "manager", "Manager"
        CASHIER = "cashier", "Cashier"

    role = models.CharField(max_length=30, choices=Role.choices, unique=True)
    covers_per_staff = models.PositiveIntegerField()

    class Meta:
        ordering = ["role"]

    def __str__(self):
        return f"{self.get_role_display()} — {self.covers_per_staff} covers/staff"


class DishPopularity(BaseModel):
    dish_name = models.CharField(max_length=200, unique=True)
    average_orders_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    class Meta:
        verbose_name_plural = "dish popularities"
        ordering = ["-average_orders_percentage"]

    def __str__(self):
        return f"{self.dish_name} ({self.average_orders_percentage}%)"
