from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.feedback.models import ForecastAccuracy
from apps.forecasting.models import DishPopularity, HistoricalCover, StaffRole
from apps.operations.models import Ingredient


@pytest.mark.django_db
class TestForecastEndpoint:
    def test_get_forecast_returns_aggregated_plan(self):
        target = date(2024, 6, 10)

        for offset in range(1, 8):
            day = target - timedelta(days=offset)
            HistoricalCover.objects.create(
                date=day,
                hour=12,
                covers=100,
                is_weekend=day.weekday() >= 5,
            )

        StaffRole.objects.create(role="waiter", covers_per_staff=20)
        StaffRole.objects.create(role="chef", covers_per_staff=30)

        DishPopularity.objects.create(dish_name="burger", average_orders_percentage=100)
        Ingredient.objects.create(
            name="beef",
            unit="kg",
            default_quantity_per_dish=0.2,
            shelf_life_days=3,
            supplier_lead_time_days=2,
        )

        client = APIClient()
        response = client.get("/forecast/", {"date": target.isoformat()}, secure=True)

        assert response.status_code == 200
        payload = response.json()

        assert payload["date"] == target.isoformat()
        assert isinstance(payload["total_covers"], int)
        assert payload["total_covers"] >= 0

        assert payload["hourly_breakdown"]
        assert sum(item["covers"] for item in payload["hourly_breakdown"]) == payload["total_covers"]

        assert payload["staff_plan"]
        assert "roles" in payload["staff_plan"][0]

        assert payload["ingredient_plan"]
        assert payload["ingredient_plan"][0]["name"] == "beef"

    def test_get_forecast_requires_valid_date(self):
        client = APIClient()
        response = client.get("/forecast/", {"date": "invalid"}, secure=True)
        assert response.status_code == 400


@pytest.mark.django_db
class TestFeedbackEndpoint:
    def test_post_feedback_records_error(self):
        client = APIClient()
        response = client.post(
            "/feedback/",
            {"predicted": 100, "actual": 120, "reason": "walk-ins"},
            format="json",
            secure=True,
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["predicted"] == 100
        assert payload["actual"] == 120
        assert payload["error"] == 20
        assert payload["error_percentage"] == 20.0
        assert payload["reason"] == "walk-ins"

        assert ForecastAccuracy.objects.filter(
            date=date.today(),
            predicted_covers=100,
            actual_covers=120,
        ).exists()

    def test_post_feedback_accepts_explicit_date(self):
        client = APIClient()
        response = client.post(
            "/feedback/",
            {"date": "2024-06-09", "predicted": 100, "actual": 110, "reason": "event"},
            format="json",
            secure=True,
        )
        assert response.status_code == 201
        assert response.json()["date"] == "2024-06-09"
        assert ForecastAccuracy.objects.filter(date="2024-06-09").exists()

    def test_post_feedback_validates_non_negative_input(self):
        client = APIClient()
        response = client.post(
            "/feedback/",
            {"predicted": -1, "actual": 120, "reason": "bad input"},
            format="json",
            secure=True,
        )
        assert response.status_code == 400
