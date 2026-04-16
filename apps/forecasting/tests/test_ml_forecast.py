from datetime import date, timedelta

import pytest

from apps.forecasting.models import HistoricalCover
from apps.forecasting.services import ML_MIN_TRAINING_SAMPLES, MLForecastService


def _make_covers(count: int, base_date: date, base_covers: int = 100) -> None:
    for i in range(count):
        day = base_date - timedelta(days=count - i)
        HistoricalCover.objects.create(
            date=day,
            hour=12,
            covers=base_covers + i,
            is_weekend=day.weekday() >= 5,
        )


@pytest.mark.django_db
class TestMLForecastServiceFallback:
    def test_falls_back_to_rule_based_when_insufficient_data(self):
        target = date(2024, 6, 10)
        _make_covers(ML_MIN_TRAINING_SAMPLES - 1, target)

        result = MLForecastService(target_date=target).predict()

        # Rule-based result has no ML adjustment label
        assert not any("ml:" in adj for adj in result.adjustments)

    def test_uses_ml_when_sufficient_data(self):
        target = date(2024, 6, 10)
        _make_covers(ML_MIN_TRAINING_SAMPLES, target)

        result = MLForecastService(target_date=target).predict()

        assert any("ml:linear_regression" in adj for adj in result.adjustments)

    def test_exact_minimum_samples_triggers_ml(self):
        target = date(2024, 6, 10)
        _make_covers(ML_MIN_TRAINING_SAMPLES, target)

        result = MLForecastService(target_date=target).predict()

        assert any("ml:" in adj for adj in result.adjustments)


@pytest.mark.django_db
class TestMLForecastServicePrediction:
    def test_returns_non_negative_prediction(self):
        target = date(2024, 6, 10)
        _make_covers(ML_MIN_TRAINING_SAMPLES, target)

        result = MLForecastService(target_date=target).predict()

        assert result.final_prediction >= 0

    def test_returns_forecast_result_with_correct_date(self):
        target = date(2024, 6, 10)
        _make_covers(ML_MIN_TRAINING_SAMPLES, target)

        result = MLForecastService(target_date=target).predict()

        assert result.target_date == target

    def test_weather_passed_through_to_result(self):
        target = date(2024, 6, 10)
        _make_covers(ML_MIN_TRAINING_SAMPLES, target)

        result = MLForecastService(target_date=target, weather="rainy").predict()

        assert result.weather == "rainy"

    def test_weekend_flag_correct_for_saturday(self):
        saturday = date(2024, 6, 8)  # Saturday
        _make_covers(ML_MIN_TRAINING_SAMPLES, saturday)

        result = MLForecastService(target_date=saturday).predict()

        assert result.is_weekend is True

    def test_weekend_flag_correct_for_monday(self):
        monday = date(2024, 6, 10)  # Monday
        _make_covers(ML_MIN_TRAINING_SAMPLES, monday)

        result = MLForecastService(target_date=monday).predict()

        assert result.is_weekend is False

    def test_prediction_learns_upward_trend(self):
        target = date(2024, 6, 20)
        # Create strongly increasing data so regression predicts higher than average
        for i in range(ML_MIN_TRAINING_SAMPLES):
            day = target - timedelta(days=ML_MIN_TRAINING_SAMPLES - i)
            HistoricalCover.objects.create(
                date=day,
                hour=12,
                covers=50 + i * 10,  # 50, 60, 70 ... strongly increasing
                is_weekend=day.weekday() >= 5,
            )

        result = MLForecastService(target_date=target).predict()

        # The projection should be above the simple average of 50..180 (avg ~115)
        simple_avg = 50 + (ML_MIN_TRAINING_SAMPLES - 1) * 10 / 2
        assert result.final_prediction > simple_avg

    def test_aggregates_multiple_hours_into_single_daily_total(self):
        # HistoricalCover is unique per (date, hour). If _load_training_data
        # groups by weather/is_weekend as well as date, a day with covers
        # spread across hours would be split into multiple training rows,
        # inflating daily_total and the sample count. This verifies correct
        # per-day aggregation.
        target = date(2024, 6, 20)
        # Create ML_MIN_TRAINING_SAMPLES - 1 single-hour days as padding
        for i in range(ML_MIN_TRAINING_SAMPLES - 1):
            day = target - timedelta(days=ML_MIN_TRAINING_SAMPLES - i)
            HistoricalCover.objects.create(
                date=day, hour=12, covers=100, is_weekend=day.weekday() >= 5,
            )
        # Final training day has covers split across 3 hours (total = 300)
        multi_hour_day = target - timedelta(days=1)
        for hour, covers in [(11, 80), (12, 120), (13, 100)]:
            HistoricalCover.objects.create(
                date=multi_hour_day, hour=hour, covers=covers,
                is_weekend=multi_hour_day.weekday() >= 5,
            )

        result = MLForecastService(target_date=target).predict()

        # ML path should have fired (not fallen back to rule-based)
        assert any("ml:linear_regression" in adj for adj in result.adjustments)
        # Sample count in the adjustment should equal ML_MIN_TRAINING_SAMPLES (not more)
        adj = next(a for a in result.adjustments if "ml:linear_regression" in a)
        assert f"samples={ML_MIN_TRAINING_SAMPLES}" in adj
