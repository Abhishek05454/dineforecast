from django.contrib import admin
from .models import Shift, InventoryItem


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["staff_name", "role", "shift_date", "start_time", "end_time", "status"]
    list_filter = ["role", "status", "shift_date"]
    search_fields = ["staff_name"]


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ["name", "unit", "current_quantity", "reorder_threshold", "needs_reorder"]
    list_filter = ["unit"]
    search_fields = ["name"]
