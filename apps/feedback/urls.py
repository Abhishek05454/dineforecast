from rest_framework.routers import DefaultRouter
from .views import GuestFeedbackViewSet, FeedbackResponseViewSet

router = DefaultRouter()
router.register("guest", GuestFeedbackViewSet, basename="guest-feedback")
router.register("responses", FeedbackResponseViewSet, basename="feedback-response")

urlpatterns = router.urls
