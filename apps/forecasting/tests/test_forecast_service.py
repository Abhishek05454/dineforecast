from datetime import date, timedelta

import pytest

from apps.forecasting.models import HistoricalCover
from apps.forecasting.services import ForecastService


def _make_covers(base_date: date, covers_by_offset: dict[int, int], hour: int = 12):
    for offset, covers in covers_by_offset.items():
        target = base_date - timedelta(days=offset)
        HistoricalCover.objects.get_or_create(
            date=target,
            hour=hour,
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

    def test_weight_redistribution_with_only_last7(self):
        target = date(2024, 6, 10)
        # Only 1 prior day — enough for last_7_days_avg but not for trend (needs ≥2)
        # Offset 7 intentionally absent so same_weekday_avg stays unavailable.
        _make_covers(target, {1: 100})
        svc = ForecastService(target)
        result = svc.predict()
        assert result.same_weekday_avg is None
        # With only last_7 available, all weight redistributes to it → base == last_7
        assert result.base_prediction == result.last_7_days_avg


# ---------------------------------------------------------------------------
# Multi-hour aggregation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMultiHourAggregation:
    def test_daily_total_sums_across_hours(self):
        """
        Two rows on the same date (different hours) should be summed,
        not averaged. 60 + 40 = 100 total covers for that day.
        """
        target = date(2024, 7, 15)
        day = target - timedelta(days=1)
        HistoricalCover.objects.create(date=day, hour=12, covers=60, is_weekend=False)
        HistoricalCover.objects.create(date=day, hour=18, covers=40, is_weekend=False)

        result = ForecastService(target).predict()
        assert result.last_7_days_avg == 100.0


# ---------------------------------------------------------------------------
# Weekend adjustment
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWeekendAdjustment:
    def test_weekend_increases_prediction(self):
        saturday = date(2024, 6, 8)
        _make_covers(saturday, {i: 100 for i in range(1, 7)})

        result = ForecastService(saturday).predict()
        assert "weekend +30%" in result.adjustments
        assert result.final_prediction > result.base_prediction

    def test_weekday_no_boost(self):
        monday = date(2024, 6, 10)
        _make_covers(monday, {i: 100 for i in range(1, 7)})

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
        _make_covers(target, {i: 100 for i in range(1, 7)})

        result = ForecastService(target, weather="rainy").predict()
        assert "rainy weather -15%" in result.adjustments
        assert result.final_prediction < result.base_prediction

    def test_snow_decreases_prediction(self):
        target = date(2024, 6, 10)
        _make_covers(target, {i: 100 for i in range(1, 7)})

        result = ForecastService(target, weather="snowy").predict()
        assert "snowy weather -30%" in result.adjustments
        assert result.final_prediction < result.base_prediction

    def test_sunny_no_penalty(self):
        target = date(2024, 6, 10)
        _make_covers(target, {i: 100 for i in range(1, 7)})

        result = ForecastService(target, weather="sunny").predict()
        assert result.adjustments == []


# ---------------------------------------------------------------------------
# Linear projection
# ---------------------------------------------------------------------------

class TestLinearProjection:
    def test_upward_trend(self):
        records = [{"date": date(2024, 1, i), "daily_total": i * 10} for i in range(1, 8)]
        projected = ForecastService._linear_projection(records)
        assert projected > records[-1]["daily_total"]

    def test_gap_in_dates_handled_correctly(self):
        # Days 1, 2, then a 5-day gap to day 8 — slope should reflect real calendar distance
        records = [
            {"date": date(2024, 1, 1), "daily_total": 100},
            {"date": date(2024, 1, 2), "daily_total": 110},
            {"date": date(2024, 1, 8), "daily_total": 170},
        ]
        projected = ForecastService._linear_projection(records)
        # Trend is upward; projection for Jan 9 should be above 170
        assert projected > 170

    def test_downward_trend_clamped_to_zero(self):
        records = [{"date": date(2024, 1, i), "daily_total": max(0, 50 - i * 10)} for i in range(1, 6)]
        projected = ForecastService._linear_projection(records)
        assert projected >= 0

    def test_flat_trend_returns_mean(self):
        records = [{"date": date(2024, 1, i), "daily_total": 50} for i in range(1, 6)]
        projected = ForecastService._linear_projection(records)
        assert abs(projected - 50) < 0.01


# ---------------------------------------------------------------------------
# Combined scenario
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCombinedScenario:
    def test_rainy_weekend_adjustments_stack(self):
        saturday = date(2024, 6, 8)
        _make_covers(saturday, {i: 100 for i in range(1, 7)})

        result = ForecastService(saturday, weather="rainy").predict()
        assert len(result.adjustments) == 2
        # base × 1.30 × 0.85 ≈ 10.5% above base
        assert result.final_prediction > result.base_prediction
