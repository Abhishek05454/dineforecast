from django.db import models


class StaffRoleChoices(models.TextChoices):
    WAITER = "waiter", "Waiter"
    CHEF = "chef", "Chef"
    BARTENDER = "bartender", "Bartender"
    MANAGER = "manager", "Manager"
    CASHIER = "cashier", "Cashier"


class UnitChoices(models.TextChoices):
    KG = "kg", "Kilograms"
    LITRE = "litre", "Litres"
    PIECE = "piece", "Pieces"
    DOZEN = "dozen", "Dozen"
