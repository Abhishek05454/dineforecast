from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

from apps.feedback.models import ForecastAccuracy
from apps.forecasting.models import DishPopularity, HistoricalCover, StaffRole
from apps.operations.models import Ingredient


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(username="tester", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestForecastEndpoint:
    def test_get_forecast_returns_aggregated_plan(self, auth_client):
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

        response = auth_client.get(
            "/api/v1/forecasting/forecast/", {"date": target.isoformat()}
        )

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
        assert payload["ingredient_plan_available"] is True
        assert payload["ingredient_plan_error"] is None

    def test_get_forecast_ingredient_plan_unavailable_when_no_dishes(self, auth_client):
        target = date(2024, 6, 10)
        for offset in range(1, 8):
            day = target - timedelta(days=offset)
            HistoricalCover.objects.create(
                date=day, hour=12, covers=100, is_weekend=day.weekday() >= 5,
            )
        response = auth_client.get(
            "/api/v1/forecasting/forecast/", {"date": target.isoformat()}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ingredient_plan_available"] is False
        assert payload["ingredient_plan_error"] is not None
        assert payload["ingredient_plan"] == []

    def test_second_request_served_from_cache(self, auth_client):
        target = date(2024, 6, 10)
        for offset in range(1, 8):
            day = target - timedelta(days=offset)
            HistoricalCover.objects.create(
                date=day, hour=12, covers=100, is_weekend=day.weekday() >= 5,
            )
        with patch("apps.forecasting.views.ForecastService") as mock_svc:
            mock_svc.return_value.predict.return_value.final_prediction = 100
            mock_svc.return_value.predict.return_value.base_prediction = 100
            mock_svc.return_value.predict.return_value.is_weekend = False
            mock_svc.return_value.predict.return_value.weather = ""
            mock_svc.return_value.predict.return_value.adjustments = []
            mock_svc.return_value.predict.return_value.last_7_days_avg = 100.0
            mock_svc.return_value.predict.return_value.same_weekday_avg = None
            mock_svc.return_value.predict.return_value.recent_trend = None
            mock_svc.return_value.predict.return_value.feedback_adjustment_factor = 1.0
            mock_svc.return_value.predict.return_value.feedback_samples = 0
            mock_svc.return_value.predict.return_value.learning_rate = 0.0
            mock_svc.return_value.predict.return_value.component_weights = {}

            auth_client.get("/api/v1/forecasting/forecast/", {"date": target.isoformat()})
            auth_client.get("/api/v1/forecasting/forecast/", {"date": target.isoformat()})
            assert mock_svc.return_value.predict.call_count == 1

    def test_feedback_submission_invalidates_forecast_cache(self, auth_client):
        target = date(2024, 6, 10)
        cache_key = f"forecast:{target.isoformat()}"
        cache.set(cache_key, {"date": target.isoformat(), "total_covers": 100})
        assert cache.get(cache_key) is not None

        auth_client.post(
            "/api/v1/feedback/forecast/",
            {"date": target.isoformat(), "predicted": 100, "actual": 120},
            format="json",
        )
        assert cache.get(cache_key) is None

    def test_get_forecast_requires_valid_date(self, auth_client):
        response = auth_client.get("/api/v1/forecasting/forecast/", {"date": "invalid"})
        assert response.status_code == 400

    def test_get_forecast_requires_authentication(self):
        client = APIClient()
        response = client.get("/api/v1/forecasting/forecast/", {"date": "2024-06-10"})
        assert response.status_code == 401


@pytest.mark.django_db
class TestFeedbackEndpoint:
    def test_post_feedback_records_error(self, auth_client):
        response = auth_client.post(
            "/api/v1/feedback/forecast/",
            {"predicted": 100, "actual": 120, "reason": "walk-ins"},
            format="json",
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

    def test_post_feedback_returns_200_on_update(self, auth_client):
        ForecastAccuracy.objects.create(
            date="2024-06-09",
            predicted_covers=90,
            actual_covers=100,
        )
        response = auth_client.post(
            "/api/v1/feedback/forecast/",
            {"date": "2024-06-09", "predicted": 100, "actual": 110, "reason": "updated"},
            format="json",
        )
        assert response.status_code == 200

    def test_post_feedback_accepts_explicit_date(self, auth_client):
        response = auth_client.post(
            "/api/v1/feedback/forecast/",
            {"date": "2024-06-09", "predicted": 100, "actual": 110, "reason": "event"},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["date"] == "2024-06-09"
        assert ForecastAccuracy.objects.filter(date="2024-06-09").exists()

    def test_post_feedback_validates_non_negative_input(self, auth_client):
        response = auth_client.post(
            "/api/v1/feedback/forecast/",
            {"predicted": -1, "actual": 120, "reason": "bad input"},
            format="json",
        )
        assert response.status_code == 400

    def test_post_feedback_zero_predicted_zero_actual_returns_zero_percentage(self, auth_client):
        response = auth_client.post(
            "/api/v1/feedback/forecast/",
            {"date": "2024-06-08", "predicted": 0, "actual": 0},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["error_percentage"] == 0.0

    def test_post_feedback_zero_predicted_nonzero_actual_returns_null_percentage(self, auth_client):
        response = auth_client.post(
            "/api/v1/feedback/forecast/",
            {"date": "2024-06-07", "predicted": 0, "actual": 50},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["error_percentage"] is None

    def test_post_feedback_requires_authentication(self):
        client = APIClient()
        response = client.post(
            "/api/v1/feedback/forecast/",
            {"predicted": 100, "actual": 120},
            format="json",
        )
        assert response.status_code == 401
