from django.db import models
from core.models import BaseModel


class Shift(BaseModel):
    class ShiftStatus(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Role(models.TextChoices):
        WAITER = "waiter", "Waiter"
        CHEF = "chef", "Chef"
        BARTENDER = "bartender", "Bartender"
        MANAGER = "manager", "Manager"
        CASHIER = "cashier", "Cashier"

    staff_name = models.CharField(max_length=150)
    role = models.CharField(max_length=30, choices=Role.choices)
    shift_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=20, choices=ShiftStatus.choices, default=ShiftStatus.SCHEDULED
    )

    class Meta:
        ordering = ["shift_date", "start_time"]
        indexes = [
            models.Index(fields=["shift_date"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.staff_name} | {self.role} | {self.shift_date}"


class Ingredient(BaseModel):
    class Unit(models.TextChoices):
        KG = "kg", "Kilograms"
        LITRE = "litre", "Litres"
        PIECE = "piece", "Pieces"
        DOZEN = "dozen", "Dozen"

    name = models.CharField(max_length=200, unique=True)
    unit = models.CharField(max_length=20, choices=Unit.choices)
    per_dish_quantity = models.DecimalField(max_digits=10, decimal_places=4)
    shelf_life_days = models.PositiveIntegerField()
    supplier_lead_time_days = models.PositiveIntegerField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.per_dish_quantity} {self.unit}/dish)"


class InventoryItem(BaseModel):
    class Unit(models.TextChoices):
        KG = "kg", "Kilograms"
        LITRE = "litre", "Litres"
        PIECE = "piece", "Pieces"
        DOZEN = "dozen", "Dozen"

    name = models.CharField(max_length=200, unique=True)
    unit = models.CharField(max_length=20, choices=Unit.choices)
    current_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    reorder_threshold = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["name"]

    @property
    def needs_reorder(self):
        return self.current_quantity <= self.reorder_threshold

    def __str__(self):
        return f"{self.name} ({self.current_quantity} {self.unit})"
