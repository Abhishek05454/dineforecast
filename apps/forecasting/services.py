import math
import numbers
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Mapping, Optional

from django.db.models import Avg, Sum

from apps.operations.models import Ingredient
from .models import DishPopularity, HistoricalCover, StaffRole

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


def _validate_hour_key_map(values: dict[int, object]) -> None:
    invalid_keys = [h for h in values if not isinstance(h, int) or isinstance(h, bool)]
    if invalid_keys:
        raise ValueError(f"Hour keys must be plain integers: {invalid_keys}")
    out_of_range = [h for h in values if not (0 <= h <= 23)]
    if out_of_range:
        raise ValueError(f"Hour keys must be in the range 0-23: {out_of_range}")


def _validate_distribution(distribution: dict[int, float]) -> None:
    if not distribution:
        raise ValueError("Distribution must not be empty.")

    _validate_hour_key_map(distribution)

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
        _validate_hour_key_map(covers_by_hour)
        invalid_covers = [h for h, c in covers_by_hour.items() if not isinstance(c, int) or isinstance(c, bool)]
        if invalid_covers:
            raise ValueError(f"Cover counts must be plain integers. Invalid hours: {invalid_covers}")
        negative = [h for h, c in covers_by_hour.items() if c < 0]
        if negative:
            raise ValueError(f"Cover counts must be non-negative. Invalid hours: {negative}")
        self.covers_by_hour = dict(covers_by_hour)

    def plan(self) -> StaffPlanResult:
        roles = list(StaffRole.objects.filter(covers_per_staff__gt=0))
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


DEFAULT_BUFFER_FRACTION: float = 0.15


@dataclass(frozen=True)
class IngredientPerDishInput:
    dish_name: str
    ingredient_name: str
    quantity_per_dish: float
    unit: str
    shelf_life_days: int
    supplier_lead_time_days: int


@dataclass
class IngredientRequirement:
    name: str
    unit: str
    base_quantity: float
    buffer_quantity: float
    total_quantity: float
    shelf_life_days: int
    supplier_lead_time_days: int
    order_days_ahead: int
    freshness_risk: bool


@dataclass
class IngredientForecastResult:
    covers: float
    buffer_fraction: float
    requirements: list[IngredientRequirement]

    def as_dict(self) -> dict[str, float]:
        return {r.name: r.total_quantity for r in self.requirements}


class IngredientForecastService:

    def __init__(
        self,
        predicted_covers: float,
        dish_popularity: Mapping[str, float] | None = None,
        ingredient_per_dish: Iterable[IngredientPerDishInput] | None = None,
        buffer_fraction: float = DEFAULT_BUFFER_FRACTION,
    ):
        if not math.isfinite(predicted_covers) or predicted_covers < 0:
            raise ValueError(
                f"predicted_covers must be a finite non-negative number (got {predicted_covers!r})."
            )
        if not math.isfinite(buffer_fraction) or not (0.10 <= buffer_fraction <= 0.20):
            raise ValueError(
                f"buffer_fraction must be between 0.10 and 0.20 (got {buffer_fraction!r})."
            )
        self.covers = predicted_covers
        self.buffer_fraction = buffer_fraction
        self.dish_popularity = self._validate_dish_popularity(dish_popularity or {})
        self.ingredient_per_dish = list(ingredient_per_dish or [])
        self._validate_recipe_lines(self.ingredient_per_dish)

    @classmethod
    def from_database(
        cls,
        predicted_covers: float,
        buffer_fraction: float = DEFAULT_BUFFER_FRACTION,
    ) -> "IngredientForecastService":
        dish_popularity = {
            d.dish_name: float(d.average_orders_percentage)
            for d in DishPopularity.objects.all()
        }
        ingredients = list(Ingredient.objects.all())
        recipe_lines: list[IngredientPerDishInput] = []
        for dish_name in dish_popularity:
            for ingredient in ingredients:
                recipe_lines.append(
                    IngredientPerDishInput(
                        dish_name=dish_name,
                        ingredient_name=ingredient.name,
                        quantity_per_dish=float(ingredient.default_quantity_per_dish),
                        unit=ingredient.unit,
                        shelf_life_days=ingredient.shelf_life_days,
                        supplier_lead_time_days=ingredient.supplier_lead_time_days,
                    )
                )
        return cls(
            predicted_covers=predicted_covers,
            dish_popularity=dish_popularity,
            ingredient_per_dish=recipe_lines,
            buffer_fraction=buffer_fraction,
        )

    def forecast(self) -> IngredientForecastResult:
        if not self.ingredient_per_dish:
            return IngredientForecastResult(
                covers=self.covers,
                buffer_fraction=self.buffer_fraction,
                requirements=[],
            )

        dish_orders = self._dish_orders()
        ingredient_totals: dict[str, float] = {}
        metadata: dict[str, IngredientPerDishInput] = {}

        for line in self.ingredient_per_dish:
            orders_for_dish = dish_orders.get(line.dish_name, 0.0)
            ingredient_totals[line.ingredient_name] = ingredient_totals.get(line.ingredient_name, 0.0) + (
                orders_for_dish * line.quantity_per_dish
            )
            if line.ingredient_name not in metadata:
                metadata[line.ingredient_name] = line

        requirements = [
            self._build_requirement(name, ingredient_totals[name], metadata[name])
            for name in sorted(ingredient_totals)
        ]

        return IngredientForecastResult(
            covers=self.covers,
            buffer_fraction=self.buffer_fraction,
            requirements=requirements,
        )

    def _dish_orders(self) -> dict[str, float]:
        if not self.dish_popularity:
            return {}
        popularity_total = sum(self.dish_popularity.values())
        if popularity_total == 0:
            return {dish_name: 0.0 for dish_name in self.dish_popularity}
        return {
            dish_name: self.covers * (popularity / popularity_total)
            for dish_name, popularity in self.dish_popularity.items()
        }

    def _build_requirement(
        self,
        ingredient_name: str,
        base_quantity: float,
        line: IngredientPerDishInput,
    ) -> IngredientRequirement:
        base = base_quantity
        buffer = base * self.buffer_fraction
        total = base + buffer
        order_days_ahead = line.supplier_lead_time_days
        freshness_risk = line.supplier_lead_time_days > line.shelf_life_days

        return IngredientRequirement(
            name=ingredient_name,
            unit=line.unit,
            base_quantity=round(base, 4),
            buffer_quantity=round(buffer, 4),
            total_quantity=round(total, 4),
            shelf_life_days=line.shelf_life_days,
            supplier_lead_time_days=line.supplier_lead_time_days,
            order_days_ahead=order_days_ahead,
            freshness_risk=freshness_risk,
        )

    @staticmethod
    def _validate_dish_popularity(
        dish_popularity: Mapping[str, float],
    ) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for dish_name, popularity in dish_popularity.items():
            if not isinstance(dish_name, str) or not dish_name.strip():
                raise ValueError("dish_popularity keys must be non-empty strings.")
            if not isinstance(popularity, numbers.Real) or isinstance(popularity, bool):
                raise ValueError(
                    f"Dish popularity must be numeric for dish {dish_name!r}."
                )
            value = float(popularity)
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"Dish popularity must be a finite non-negative number for dish {dish_name!r}."
                )
            normalized[dish_name] = value
        return normalized

    @staticmethod
    def _validate_recipe_lines(lines: list[IngredientPerDishInput]) -> None:
        by_ingredient: dict[str, tuple[str, int, int]] = {}

        for line in lines:
            if (
                not isinstance(line.dish_name, str)
                or not line.dish_name.strip()
                or not isinstance(line.ingredient_name, str)
                or not line.ingredient_name.strip()
            ):
                raise ValueError(
                    "dish_name and ingredient_name must be non-empty strings."
                )
            if not isinstance(line.quantity_per_dish, numbers.Real) or isinstance(
                line.quantity_per_dish,
                bool,
            ):
                raise ValueError(
                    f"quantity_per_dish must be numeric for ingredient {line.ingredient_name!r}."
                )
            if not math.isfinite(float(line.quantity_per_dish)) or line.quantity_per_dish < 0:
                raise ValueError(
                    f"quantity_per_dish must be finite and non-negative for ingredient {line.ingredient_name!r}."
                )
            if line.shelf_life_days < 0 or line.supplier_lead_time_days < 0:
                raise ValueError(
                    f"shelf_life_days and supplier_lead_time_days must be non-negative for ingredient {line.ingredient_name!r}."
                )

            existing = by_ingredient.get(line.ingredient_name)
            current = (line.unit, line.shelf_life_days, line.supplier_lead_time_days)
            if existing is None:
                by_ingredient[line.ingredient_name] = current
            elif existing != current:
                raise ValueError(
                    f"Ingredient metadata must be consistent across dishes for ingredient {line.ingredient_name!r}."
                )
