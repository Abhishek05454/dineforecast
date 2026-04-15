import math
import numbers
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from django.db.models import Avg, Sum

from .models import HistoricalCover, StaffRole

DEFAULT_HOURLY_DISTRIBUTION: dict[int, float] = {
    12: 0.10,
    13: 0.25,
    14: 0.20,
    19: 0.20,
    20: 0.15,
    21: 0.10,
}


@dataclass
class HourlySlot:
    hour: int
    covers: int
    share: float


@dataclass
class HourlyDistributionResult:
    total_covers: float
    slots: list[HourlySlot]

    def as_dict(self) -> dict[int, int]:
        return {slot.hour: slot.covers for slot in self.slots}


def distribute_covers_by_hour(
    total_covers: float,
    distribution: dict[int, float] | None = None,
) -> HourlyDistributionResult:
    if not math.isfinite(total_covers) or total_covers < 0:
        raise ValueError(
            f"total_covers must be a finite non-negative number (got {total_covers!r})."
        )

    if distribution is None:
        distribution = DEFAULT_HOURLY_DISTRIBUTION

    _validate_distribution(distribution)

    raw_total = sum(distribution.values())
    normalized = {h: s / raw_total for h, s in distribution.items()}

    sorted_items = sorted(normalized.items())
    slots = _allocate_covers(total_covers, sorted_items)

    return HourlyDistributionResult(total_covers=total_covers, slots=slots)


def _allocate_covers(
    total_covers: float,
    sorted_items: list[tuple[int, float]],
) -> list[HourlySlot]:
    target = round(total_covers)
    floored = [(hour, share, math.floor(total_covers * share)) for hour, share in sorted_items]
    allocated = sum(c for _, _, c in floored)
    remainder = target - allocated

    fractional_parts = [
        (total_covers * share) - covers
        for _, share, covers in floored
    ]
    descending = sorted(range(len(floored)), key=lambda i: fractional_parts[i], reverse=True)

    covers_list = [c for _, _, c in floored]
    for i in range(remainder):
        covers_list[descending[i]] += 1

    return [
        HourlySlot(hour=hour, covers=covers_list[idx], share=share)
        for idx, (hour, share, _) in enumerate(floored)
    ]


def _validate_distribution(distribution: dict[int, float]) -> None:
    if not distribution:
        raise ValueError("Distribution must not be empty.")

    invalid_hour_types = [h for h in distribution if not isinstance(h, int) or isinstance(h, bool)]
    if invalid_hour_types:
        raise ValueError(f"Hour keys must be plain integers: {invalid_hour_types}")

    invalid_hours = [h for h in distribution if not (0 <= h <= 23)]
    if invalid_hours:
        raise ValueError(f"Hours out of range 0–23: {invalid_hours}")

    non_numeric_shares = [h for h, s in distribution.items() if not isinstance(s, numbers.Real) or isinstance(s, bool)]
    if non_numeric_shares:
        raise ValueError(f"Shares must be finite real numbers. Invalid hours: {non_numeric_shares}")

    non_finite_shares = [h for h, s in distribution.items() if not math.isfinite(s)]
    if non_finite_shares:
        raise ValueError(f"Shares must be finite real numbers. Invalid hours: {non_finite_shares}")

    negative_shares = [h for h, s in distribution.items() if s < 0]
    if negative_shares:
        raise ValueError(f"Shares must be non-negative. Invalid hours: {negative_shares}")

    total = sum(distribution.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(
            f"Distribution shares must sum to 1.0 (got {total:.4f})."
        )


@dataclass
class ForecastResult:
    target_date: date
    base_prediction: float
    final_prediction: float
    is_weekend: bool
    weather: str
    adjustments: list[str] = field(default_factory=list)

    last_7_days_avg: Optional[float] = None
    same_weekday_avg: Optional[float] = None
    recent_trend: Optional[float] = None


class ForecastService:

    WEIGHT_LAST_7 = 0.50
    WEIGHT_WEEKDAY = 0.30
    WEIGHT_TREND = 0.20

    WEEKEND_BOOST = 0.30
    RAIN_PENALTY = 0.15
    SNOWY_PENALTY = 0.30

    TREND_WINDOW = 7
    WEEKDAY_LOOKBACK = 8

    def __init__(self, target_date: date, weather: str = ""):
        self.target_date = target_date
        self.weather = weather.lower().strip()
        self.is_weekend = target_date.weekday() >= 5

    def predict(self) -> ForecastResult:
        last_7 = self._last_7_days_avg()
        weekday = self._same_weekday_avg()
        trend = self._recent_trend(last_7_fallback=last_7)

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

    def _last_7_days_avg(self) -> Optional[float]:
        start = self.target_date - timedelta(days=7)
        end = self.target_date - timedelta(days=1)
        return self._daily_total_avg(start, end)

    def _same_weekday_avg(self) -> Optional[float]:
        dates = [
            self.target_date - timedelta(weeks=i)
            for i in range(1, self.WEEKDAY_LOOKBACK + 1)
        ]
        result = (
            HistoricalCover.objects
            .filter(date__in=dates)
            .values("date")
            .annotate(daily_total=Sum("covers"))
            .aggregate(avg=Avg("daily_total"))
        )
        return result["avg"]

    def _recent_trend(self, last_7_fallback: Optional[float] = None) -> Optional[float]:
        start = self.target_date - timedelta(days=self.TREND_WINDOW)
        end = self.target_date - timedelta(days=1)

        records = list(
            HistoricalCover.objects
            .filter(date__gte=start, date__lte=end)
            .values("date")
            .annotate(daily_total=Sum("covers"))
            .order_by("date")
        )

        if len(records) < 2:
            return last_7_fallback

        return self._linear_projection(records)

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

    def _daily_total_avg(self, start: date, end: date) -> Optional[float]:
        result = (
            HistoricalCover.objects
            .filter(date__gte=start, date__lte=end)
            .values("date")
            .annotate(daily_total=Sum("covers"))
            .aggregate(avg=Avg("daily_total"))
        )
        return result["avg"]

    def _weighted_average(
        self,
        last_7: Optional[float],
        weekday: Optional[float],
        trend: Optional[float],
    ) -> float:
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
        first_ordinal = records[0]["date"].toordinal()
        xs = [r["date"].toordinal() - first_ordinal for r in records]
        ys = [r["daily_total"] for r in records]
        n = len(records)

        x_mean = sum(xs) / n
        y_mean = sum(ys) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        denominator = sum((x - x_mean) ** 2 for x in xs)

        if denominator == 0:
            return y_mean

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        next_day_ordinal = records[-1]["date"].toordinal() + 1 - first_ordinal
        projected = slope * next_day_ordinal + intercept
        return max(0.0, projected)


@dataclass
class RoleRequirement:
    role: str
    covers_per_staff: int
    staff_required: int


@dataclass
class HourlyStaffingResult:
    hour: int
    covers: int
    roles: list[RoleRequirement]

    def total_staff(self) -> int:
        return sum(r.staff_required for r in self.roles)


@dataclass
class StaffPlanResult:
    hours: list[HourlyStaffingResult]

    def as_dict(self) -> dict[int, dict[str, int]]:
        return {
            h.hour: {r.role: r.staff_required for r in h.roles}
            for h in self.hours
        }


class StaffPlanningService:

    def __init__(self, covers_by_hour: dict[int, int]):
        if not covers_by_hour:
            raise ValueError("covers_by_hour must not be empty.")
        invalid = [h for h in covers_by_hour if not isinstance(h, int) or isinstance(h, bool)]
        if invalid:
            raise ValueError(f"Hour keys must be plain integers: {invalid}")
        negative = [h for h, c in covers_by_hour.items() if c < 0]
        if negative:
            raise ValueError(f"Cover counts must be non-negative. Invalid hours: {negative}")
        self.covers_by_hour = covers_by_hour

    def plan(self) -> StaffPlanResult:
        roles = list(StaffRole.objects.all())
        hours = []
        for hour in sorted(self.covers_by_hour):
            covers = self.covers_by_hour[hour]
            role_reqs = [
                RoleRequirement(
                    role=r.role,
                    covers_per_staff=r.covers_per_staff,
                    staff_required=math.ceil(covers / r.covers_per_staff) if covers > 0 else 0,
                )
                for r in roles
            ]
            hours.append(HourlyStaffingResult(hour=hour, covers=covers, roles=role_reqs))
        return StaffPlanResult(hours=hours)
