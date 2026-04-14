from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/forecasting/", include("apps.forecasting.urls")),
    path("api/v1/operations/", include("apps.operations.urls")),
    path("api/v1/feedback/", include("apps.feedback.urls")),
]
