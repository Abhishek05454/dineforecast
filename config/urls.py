from django.contrib import admin
from django.urls import path, include

from apps.feedback.views import ForecastFeedbackAPIView
from apps.forecasting.views import ForecastAPIView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("forecast/", ForecastAPIView.as_view(), name="forecast-summary"),
    path("feedback/", ForecastFeedbackAPIView.as_view(), name="forecast-feedback"),
    path("api/v1/forecasting/", include("apps.forecasting.urls")),
    path("api/v1/operations/", include("apps.operations.urls")),
    path("api/v1/feedback/", include("apps.feedback.urls")),
]
