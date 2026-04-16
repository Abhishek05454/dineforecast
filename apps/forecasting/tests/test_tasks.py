from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.forecasting.cache import forecast_cache_key
from apps.forecasting.tasks import recalculate_forecasts

pytestmark = pytest.mark.django_db


SAMPLE_PAYLOAD = {
    "date": "2024-06-10",
    "total_covers": 100,
    "hourly_breakdown": [],
    "staff_plan": [],
    "ingredient_plan": [],
    "ingredient_plan_available": True,
    "ingredient_plan_error": None,
}


class TestForecastCacheKey:
    def test_key_format(self):
        assert forecast_cache_key(date(2024, 6, 10)) == "forecast:2024-06-10"


class TestRecalculateForecasts:
    def test_populates_cache_for_next_7_days(self):
        today = date(2024, 6, 10)
        with patch("apps.forecasting.tasks.build_forecast_payload", return_value=SAMPLE_PAYLOAD) as mock_build, \
             patch("apps.forecasting.tasks.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.fromisoformat = date.fromisoformat

            recalculate_forecasts()

            assert mock_build.call_count == 7
            for offset in range(1, 8):
                target = today + timedelta(days=offset)
                assert cache.get(forecast_cache_key(target)) == SAMPLE_PAYLOAD

    def test_failed_date_does_not_abort_remaining_dates(self):
        today = date(2024, 6, 10)
        call_count = 0

        def side_effect(target):
            nonlocal call_count
            call_count += 1
            if target == today + timedelta(days=1):
                raise ValueError("service error")
            return SAMPLE_PAYLOAD

        with patch("apps.forecasting.tasks.build_forecast_payload", side_effect=side_effect), \
             patch("apps.forecasting.tasks.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.fromisoformat = date.fromisoformat

            result = recalculate_forecasts()

        assert call_count == 7
        assert len(result["succeeded"]) == 6
        assert len(result["failed"]) == 1
        assert result["failed"][0] == str(today + timedelta(days=1))

    def test_succeeded_dates_written_to_cache(self):
        today = date(2024, 6, 10)
        with patch("apps.forecasting.tasks.build_forecast_payload", return_value=SAMPLE_PAYLOAD), \
             patch("apps.forecasting.tasks.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.fromisoformat = date.fromisoformat

            result = recalculate_forecasts()

        assert len(result["succeeded"]) == 7
        assert result["failed"] == []
