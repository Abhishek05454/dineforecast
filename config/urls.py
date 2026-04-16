from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/forecasting/", include("apps.forecasting.urls")),
    path("api/v1/operations/", include("apps.operations.urls")),
    path("api/v1/feedback/", include("apps.feedback.urls")),
]
