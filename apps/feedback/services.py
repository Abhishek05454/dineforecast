import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

from .models import ForecastAccuracy


@dataclass(frozen=True)
class FeedbackLearningSnapshot:
    sample_size: int
    mean_error: float
    mean_abs_percentage_error: float
    mean_signed_percentage_error: float
    learning_rate: float
    adjustment_factor: float
    weights: dict[str, float]


class ForecastFeedbackService:

    DEFAULT_LOOKBACK_DAYS = 30
    DEFAULT_LEARNING_RATE = 0.20
    MAX_ADJUSTMENT_FRACTION = 0.30
    MIN_WEIGHT = 0.05

    def __init__(
        self,
        base_weights: Mapping[str, float],
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        learning_rate: float = DEFAULT_LEARNING_RATE,
    ):
        if not base_weights:
            raise ValueError("base_weights must not be empty.")
        if lookback_days <= 0:
            raise ValueError("lookback_days must be a positive integer.")
        if not math.isfinite(learning_rate) or not (0 < learning_rate <= 1):
            raise ValueError("learning_rate must be in the range (0, 1].")

        self.base_weights = self._normalize_weights(dict(base_weights))
        self.lookback_days = lookback_days
        self.learning_rate = learning_rate

    @staticmethod
    def record_feedback(
        forecast_date: date,
        predicted_covers: int,
        actual_covers: int,
        reason: str = "",
    ) -> ForecastAccuracy:
        if predicted_covers < 0 or actual_covers < 0:
            raise ValueError("predicted_covers and actual_covers must be non-negative.")
        row, created = ForecastAccuracy.objects.update_or_create(
            date=forecast_date,
            defaults={
                "predicted_covers": predicted_covers,
                "actual_covers": actual_covers,
                "reason": reason,
            },
        )
        return row, created

    def build_snapshot(self, as_of: date) -> FeedbackLearningSnapshot:
        window_start = as_of - timedelta(days=self.lookback_days)
        records = list(
            ForecastAccuracy.objects.filter(date__gte=window_start, date__lt=as_of).order_by("-date")
        )

        if not records:
            return FeedbackLearningSnapshot(
                sample_size=0,
                mean_error=0.0,
                mean_abs_percentage_error=0.0,
                mean_signed_percentage_error=0.0,
                learning_rate=0.0,
                adjustment_factor=1.0,
                weights=dict(self.base_weights),
            )

        errors = [r.actual_covers - r.predicted_covers for r in records]
        signed_percentage_errors = [
            (r.actual_covers - r.predicted_covers) / max(r.predicted_covers, 1)
            for r in records
        ]
        abs_percentage_errors = [abs(e) for e in signed_percentage_errors]

        mean_error = sum(errors) / len(errors)
        mean_signed = sum(signed_percentage_errors) / len(signed_percentage_errors)
        mean_abs = sum(abs_percentage_errors) / len(abs_percentage_errors)

        maturity = min(1.0, len(records) / 10)
        effective_learning_rate = self.learning_rate * maturity

        raw_factor = 1 + (effective_learning_rate * mean_signed)
        min_factor = 1 - self.MAX_ADJUSTMENT_FRACTION
        max_factor = 1 + self.MAX_ADJUSTMENT_FRACTION
        adjustment_factor = min(max(raw_factor, min_factor), max_factor)

        learned_weights = self._learn_weights(
            mean_signed_percentage_error=mean_signed,
            effective_learning_rate=effective_learning_rate,
        )

        return FeedbackLearningSnapshot(
            sample_size=len(records),
            mean_error=mean_error,
            mean_abs_percentage_error=mean_abs,
            mean_signed_percentage_error=mean_signed,
            learning_rate=effective_learning_rate,
            adjustment_factor=adjustment_factor,
            weights=learned_weights,
        )

    def _learn_weights(
        self,
        mean_signed_percentage_error: float,
        effective_learning_rate: float,
    ) -> dict[str, float]:
        if "trend" not in self.base_weights:
            return dict(self.base_weights)

        trend_shift = effective_learning_rate * mean_signed_percentage_error
        raw = dict(self.base_weights)
        raw["trend"] = raw["trend"] + trend_shift

        conservative_keys = [k for k in ("last_7", "weekday") if k in raw]
        if conservative_keys:
            total_pull = trend_shift
            base_total = sum(self.base_weights[k] for k in conservative_keys)
            if base_total > 0:
                for key in conservative_keys:
                    share = self.base_weights[key] / base_total
                    raw[key] = raw[key] - (total_pull * share)

        clamped = {
            key: max(self.MIN_WEIGHT, value)
            for key, value in raw.items()
        }
        return self._normalize_weights(clamped)

    @staticmethod
    def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        for key, value in weights.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Weight for {key!r} must be a positive finite number.")
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
