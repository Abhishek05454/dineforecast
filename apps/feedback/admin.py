from django.contrib import admin
from .models import GuestFeedback, FeedbackResponse, ForecastAccuracy


@admin.register(GuestFeedback)
class GuestFeedbackAdmin(admin.ModelAdmin):
    list_display = ["visit_date", "category", "rating", "guest_name", "is_resolved"]
    list_filter = ["category", "rating", "is_resolved"]
    search_fields = ["guest_name", "comment"]
    list_editable = ["is_resolved"]


@admin.register(FeedbackResponse)
class FeedbackResponseAdmin(admin.ModelAdmin):
    list_display = ["feedback", "responded_by", "created_at"]
    search_fields = ["responded_by", "message"]


@admin.register(ForecastAccuracy)
class ForecastAccuracyAdmin(admin.ModelAdmin):
    list_display = ["date", "predicted_covers", "actual_covers", "variance", "accuracy_percentage"]
    search_fields = ["reason"]
