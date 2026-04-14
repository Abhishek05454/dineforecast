from datetime import date, timedelta

import pytest

from apps.forecasting.models import HistoricalCover
from apps.forecasting.services import ForecastService


def _make_covers(base_date: date, covers_by_offset: dict[int, int]):
    """
    Helper: create HistoricalCover rows.
    covers_by_offset = {days_before_target: covers}
    """
    for offset, covers in covers_by_offset.items():
        target = base_date - timedelta(days=offset)
        HistoricalCover.objects.get_or_create(
            date=target,
            hour=12,
            defaults={"covers": covers, "is_weekend": target.weekday() >= 5},
        )


# ---------------------------------------------------------------------------
# Weighted average
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWeightedAverage:
    def test_returns_zero_when_no_data(self):
        svc = ForecastService(date(2024, 6, 10))
        result = svc.predict()
        assert result.final_prediction == 0.0

    def test_uses_only_available_components(self):
        target = date(2024, 6, 10)
        _make_covers(target, {1: 100, 2: 100, 3: 100, 4: 100, 5: 100, 6: 100, 7: 100})
        svc = ForecastService(target)
        result = svc.predict()
        # All data is within last-7, no weekday history → base should reflect last-7
        assert result.base_prediction > 0


# ---------------------------------------------------------------------------
# Weekend adjustment
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWeekendAdjustment:
    def test_weekend_increases_prediction(self):
        # Saturday
        saturday = date(2024, 6, 8)
        _make_covers(saturday, {i: 100 for i in range(1, 8)})

        result = ForecastService(saturday).predict()
        assert "weekend +30%" in result.adjustments
        assert result.final_prediction > result.base_prediction

    def test_weekday_no_boost(self):
        # Monday
        monday = date(2024, 6, 10)
        _make_covers(monday, {i: 100 for i in range(1, 8)})

        result = ForecastService(monday).predict()
        assert not any("weekend" in a for a in result.adjustments)
        assert result.final_prediction == result.base_prediction


# ---------------------------------------------------------------------------
# Weather adjustment
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWeatherAdjustment:
    def test_rain_decreases_prediction(self):
        target = date(2024, 6, 10)
        _make_covers(target, {i: 100 for i in range(1, 8)})

        result = ForecastService(target, weather="rainy").predict()
        assert "rainy weather -15%" in result.adjustments
        assert result.final_prediction < result.base_prediction

    def test_snow_decreases_prediction(self):
        target = date(2024, 6, 10)
        _make_covers(target, {i: 100 for i in range(1, 8)})

        result = ForecastService(target, weather="snowy").predict()
        assert "snowy weather -30%" in result.adjustments
        assert result.final_prediction < result.base_prediction

    def test_sunny_no_penalty(self):
        target = date(2024, 6, 10)
        _make_covers(target, {i: 100 for i in range(1, 8)})

        result = ForecastService(target, weather="sunny").predict()
        assert result.adjustments == []


# ---------------------------------------------------------------------------
# Linear projection
# ---------------------------------------------------------------------------

class TestLinearProjection:
    def test_upward_trend(self):
        records = [{"date": date(2024, 1, i), "covers": i * 10} for i in range(1, 8)]
        projected = ForecastService._linear_projection(records)
        assert projected > records[-1]["covers"]

    def test_downward_trend_clamped_to_zero(self):
        records = [{"date": date(2024, 1, i), "covers": max(0, 50 - i * 10)} for i in range(1, 6)]
        projected = ForecastService._linear_projection(records)
        assert projected >= 0

    def test_flat_trend_returns_mean(self):
        records = [{"date": date(2024, 1, i), "covers": 50} for i in range(1, 6)]
        projected = ForecastService._linear_projection(records)
        assert abs(projected - 50) < 0.01


# ---------------------------------------------------------------------------
# Combined scenario
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCombinedScenario:
    def test_rainy_weekend_adjustments_stack(self):
        saturday = date(2024, 6, 8)
        _make_covers(saturday, {i: 100 for i in range(1, 8)})

        result = ForecastService(saturday, weather="rainy").predict()
        assert len(result.adjustments) == 2
        # +30% then -15% → net ~10.5% above base
        assert result.final_prediction > result.base_prediction
