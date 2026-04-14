from rest_framework import serializers
from .models import Shift, InventoryItem


class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = [
            "id", "staff_name", "role", "shift_date",
            "start_time", "end_time", "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        if attrs.get("start_time") and attrs.get("end_time"):
            if attrs["start_time"] >= attrs["end_time"]:
                raise serializers.ValidationError("start_time must be before end_time.")
        return attrs


class InventoryItemSerializer(serializers.ModelSerializer):
    needs_reorder = serializers.BooleanField(read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            "id", "name", "unit", "current_quantity",
            "reorder_threshold", "unit_cost", "needs_reorder",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "needs_reorder", "created_at", "updated_at"]
