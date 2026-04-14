from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import GuestFeedback, FeedbackResponse
from .serializers import GuestFeedbackSerializer, FeedbackResponseSerializer


class GuestFeedbackViewSet(viewsets.ModelViewSet):
    queryset = GuestFeedback.objects.select_related("response").all()
    serializer_class = GuestFeedbackSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["visit_date", "category", "rating", "is_resolved"]
    search_fields = ["guest_name", "comment"]
    ordering_fields = ["visit_date", "rating"]


class FeedbackResponseViewSet(viewsets.ModelViewSet):
    queryset = FeedbackResponse.objects.select_related("feedback").all()
    serializer_class = FeedbackResponseSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["feedback"]
