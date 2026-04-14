from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Shift, InventoryItem
from .serializers import ShiftSerializer, InventoryItemSerializer


class ShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["shift_date", "role", "status"]
    search_fields = ["staff_name"]
    ordering_fields = ["shift_date", "start_time"]


class InventoryItemViewSet(viewsets.ModelViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["unit"]
    search_fields = ["name"]
    ordering_fields = ["name", "current_quantity"]
