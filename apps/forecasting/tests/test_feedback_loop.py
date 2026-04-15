from datetime import date, timedelta

import pytest

from apps.feedback.services import ForecastFeedbackService
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


@pytest.mark.django_db
class TestForecastFeedbackLoop:
    def test_underprediction_history_increases_future_forecast(self):
        target = date(2024, 6, 10)
        _make_covers(target, {1: 100, 2: 100, 3: 100, 4: 100})

        ForecastFeedbackService.record_feedback(target - timedelta(days=1), 100, 120, "unexpected walk-ins")
        ForecastFeedbackService.record_feedback(target - timedelta(days=2), 100, 125, "local event")
        ForecastFeedbackService.record_feedback(target - timedelta(days=3), 100, 115, "holiday spillover")

        result = ForecastService(target).predict()

        assert result.feedback_samples == 3
        assert result.feedback_adjustment_factor > 1.0
        assert result.final_prediction > result.base_prediction
        assert any("feedback" in item for item in result.adjustments)
        assert result.component_weights["trend"] > ForecastService.WEIGHT_TREND

    def test_overprediction_history_decreases_future_forecast(self):
        target = date(2024, 6, 10)
        _make_covers(target, {1: 100, 2: 100, 3: 100, 4: 100})

        ForecastFeedbackService.record_feedback(target - timedelta(days=1), 120, 90, "rain impact")
        ForecastFeedbackService.record_feedback(target - timedelta(days=2), 130, 95, "cancellations")
        ForecastFeedbackService.record_feedback(target - timedelta(days=3), 110, 85, "low footfall")

        result = ForecastService(target).predict()

        assert result.feedback_samples == 3
        assert result.feedback_adjustment_factor < 1.0
        assert result.final_prediction < result.base_prediction
        assert result.component_weights["trend"] < ForecastService.WEIGHT_TREND

    def test_without_feedback_history_model_remains_neutral(self):
        target = date(2024, 6, 10)
        _make_covers(target, {1: 100, 2: 100})

        result = ForecastService(target).predict()

        assert result.feedback_samples == 0
        assert result.feedback_adjustment_factor == 1.0
        assert result.learning_rate == 0.0
        assert result.component_weights["last_7"] == pytest.approx(
            ForecastService.WEIGHT_LAST_7,
            abs=0.0001,
        )
        assert result.component_weights["weekday"] == pytest.approx(
            ForecastService.WEIGHT_WEEKDAY,
            abs=0.0001,
        )
        assert result.component_weights["trend"] == pytest.approx(
            ForecastService.WEIGHT_TREND,
            abs=0.0001,
        )
