from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from django.db.models import Avg, QuerySet

from .models import HistoricalCover


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    target_date: date
    base_prediction: float
    final_prediction: float
    is_weekend: bool
    weather: str
    adjustments: list[str] = field(default_factory=list)

    # component scores (for transparency / debugging)
    last_7_days_avg: Optional[float] = None
    same_weekday_avg: Optional[float] = None
    recent_trend: Optional[float] = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ForecastService:
    """
    Predicts total covers (number of customers) for a given date.

    Weighted average formula
    ------------------------
    base = (last_7_days_avg * 0.50)
         + (same_weekday_avg * 0.30)
         + (recent_trend     * 0.20)

    Adjustments applied on top of the base:
      +30%  if the target date is a Saturday or Sunday
      -15%  if weather is rainy
      -30%  if weather is stormy (future-proof)
    """

    WEIGHT_LAST_7 = 0.50
    WEIGHT_WEEKDAY = 0.30
    WEIGHT_TREND = 0.20

    WEEKEND_BOOST = 0.30
    RAIN_PENALTY = 0.15
    SNOWY_PENALTY = 0.30

    TREND_WINDOW = 7     # days used to compute recent trend slope
    WEEKDAY_LOOKBACK = 8  # how many same-weekday records to average

    def __init__(self, target_date: date, weather: str = ""):
        self.target_date = target_date
        self.weather = weather.lower().strip()
        self.is_weekend = target_date.weekday() >= 5  # Mon=0 … Sun=6

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self) -> ForecastResult:
        last_7 = self._last_7_days_avg()
        weekday = self._same_weekday_avg()
        trend = self._recent_trend()

        base = self._weighted_average(last_7, weekday, trend)
        final, adjustments = self._apply_adjustments(base)

        return ForecastResult(
            target_date=self.target_date,
            base_prediction=round(base, 2),
            final_prediction=round(final, 2),
            is_weekend=self.is_weekend,
            weather=self.weather,
            adjustments=adjustments,
            last_7_days_avg=round(last_7, 2) if last_7 is not None else None,
            same_weekday_avg=round(weekday, 2) if weekday is not None else None,
            recent_trend=round(trend, 2) if trend is not None else None,
        )

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------

    def _last_7_days_avg(self) -> Optional[float]:
        """
        Average daily covers over the 7 days immediately before the target.
        Captures the most recent general traffic level.
        """
        start = self.target_date - timedelta(days=7)
        end = self.target_date - timedelta(days=1)
        return self._daily_avg(start, end)

    def _same_weekday_avg(self) -> Optional[float]:
        """
        Average daily covers for the same weekday over recent weeks.
        Monday traffic differs from Friday traffic — this corrects for that.
        """
        dates = [
            self.target_date - timedelta(weeks=i)
            for i in range(1, self.WEEKDAY_LOOKBACK + 1)
        ]
        result = (
            HistoricalCover.objects
            .filter(date__in=dates)
            .values("date")
            .annotate(daily=Avg("covers"))
            .aggregate(avg=Avg("daily"))
        )
        return result["avg"]

    def _recent_trend(self) -> Optional[float]:
        """
        Linear trend over the last TREND_WINDOW days.
        Measures whether covers are growing or shrinking recently.
        Returns the projected value for tomorrow based on that slope.
        """
        start = self.target_date - timedelta(days=self.TREND_WINDOW)
        end = self.target_date - timedelta(days=1)

        records = list(
            HistoricalCover.objects
            .filter(date__gte=start, date__lte=end)
            .values("date", "covers")
            .order_by("date")
        )

        if len(records) < 2:
            return self._last_7_days_avg()  # fall back if not enough data

        return self._linear_projection(records)

    # ------------------------------------------------------------------
    # Adjustments
    # ------------------------------------------------------------------

    def _apply_adjustments(self, base: float) -> tuple[float, list[str]]:
        value = base
        applied = []

        if self.is_weekend:
            value *= (1 + self.WEEKEND_BOOST)
            applied.append(f"weekend +{int(self.WEEKEND_BOOST * 100)}%")

        if self.weather == HistoricalCover.Weather.RAINY:
            value *= (1 - self.RAIN_PENALTY)
            applied.append(f"rainy weather -{int(self.RAIN_PENALTY * 100)}%")

        if self.weather == HistoricalCover.Weather.SNOWY:
            value *= (1 - self.SNOWY_PENALTY)
            applied.append(f"snowy weather -{int(self.SNOWY_PENALTY * 100)}%")

        return value, applied

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _daily_avg(self, start: date, end: date) -> Optional[float]:
        """Sum covers per day, then average across days in the range."""
        result = (
            HistoricalCover.objects
            .filter(date__gte=start, date__lte=end)
            .values("date")
            .annotate(daily=Avg("covers"))
            .aggregate(avg=Avg("daily"))
        )
        return result["avg"]

    def _weighted_average(
        self,
        last_7: Optional[float],
        weekday: Optional[float],
        trend: Optional[float],
    ) -> float:
        """
        Combine the three components with their weights.
        If a component has no data, redistribute its weight equally
        among the available components so the weights always sum to 1.
        """
        components = [
            (last_7, self.WEIGHT_LAST_7),
            (weekday, self.WEIGHT_WEEKDAY),
            (trend, self.WEIGHT_TREND),
        ]
        available = [(v, w) for v, w in components if v is not None]

        if not available:
            return 0.0

        total_weight = sum(w for _, w in available)
        return sum(v * (w / total_weight) for v, w in available)

    @staticmethod
    def _linear_projection(records: list[dict]) -> float:
        """
        Least-squares linear regression on (day_index, covers) pairs.
        Returns the projected covers for the next day (index = n).
        """
        n = len(records)
        xs = list(range(n))
        ys = [r["covers"] for r in records]

        x_mean = sum(xs) / n
        y_mean = sum(ys) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        denominator = sum((x - x_mean) ** 2 for x in xs)

        if denominator == 0:
            return y_mean

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        projected = slope * n + intercept
        return max(0.0, projected)  # covers can't be negative
