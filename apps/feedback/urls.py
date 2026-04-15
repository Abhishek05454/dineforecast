from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ForecastFeedbackAPIView, GuestFeedbackViewSet, FeedbackResponseViewSet

router = DefaultRouter()
router.register("guest", GuestFeedbackViewSet, basename="guest-feedback")
router.register("responses", FeedbackResponseViewSet, basename="feedback-response")

urlpatterns = router.urls + [
    path("forecast/", ForecastFeedbackAPIView.as_view(), name="forecast-feedback"),
]
