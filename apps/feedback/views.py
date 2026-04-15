from datetime import date

from rest_framework import filters, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .models import GuestFeedback, FeedbackResponse
from .serializers import (
    FeedbackResponseSerializer,
    ForecastFeedbackCreateSerializer,
    ForecastFeedbackResponseSerializer,
    GuestFeedbackSerializer,
)
from .services import ForecastFeedbackService


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


class ForecastFeedbackAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ForecastFeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        predicted = serializer.validated_data["predicted"]
        actual = serializer.validated_data["actual"]
        reason = serializer.validated_data.get("reason", "")
        feedback_date = serializer.validated_data["date"] or date.today()
        record, created = ForecastFeedbackService.record_feedback(
            forecast_date=feedback_date,
            predicted_covers=predicted,
            actual_covers=actual,
            reason=reason,
        )

        error = actual - predicted
        error_percentage = round((error / max(predicted, 1)) * 100, 2)

        response_payload = {
            "date": record.date,
            "predicted": record.predicted_covers,
            "actual": record.actual_covers,
            "error": error,
            "error_percentage": error_percentage,
            "reason": record.reason,
        }
        response_serializer = ForecastFeedbackResponseSerializer(response_payload)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(response_serializer.data, status=http_status)
