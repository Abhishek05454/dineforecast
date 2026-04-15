from rest_framework import serializers
from .models import GuestFeedback, FeedbackResponse


class FeedbackResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackResponse
        fields = ["id", "responded_by", "message", "created_at"]
        read_only_fields = ["id", "created_at"]


class GuestFeedbackSerializer(serializers.ModelSerializer):
    response = FeedbackResponseSerializer(read_only=True)

    class Meta:
        model = GuestFeedback
        fields = [
            "id", "visit_date", "category", "rating", "comment",
            "guest_name", "is_resolved", "response", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ForecastFeedbackCreateSerializer(serializers.Serializer):
    date = serializers.DateField(required=False, default=None)
    predicted = serializers.IntegerField(min_value=0)
    actual = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class ForecastFeedbackResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    predicted = serializers.IntegerField(min_value=0)
    actual = serializers.IntegerField(min_value=0)
    error = serializers.IntegerField()
    error_percentage = serializers.FloatField(allow_null=True)
    reason = serializers.CharField()
