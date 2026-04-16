import logging
from datetime import date

from .serializers import ForecastResponseSerializer
from .services import (
    ForecastService,
    IngredientForecastService,
    StaffPlanningService,
    distribute_covers_by_hour,
)

logger = logging.getLogger(__name__)


def forecast_cache_key(forecast_date: date) -> str:
    return f"forecast:{forecast_date.isoformat()}"


def build_forecast_payload(target: date) -> dict:
    forecast_result = ForecastService(target_date=target).predict()
    total_covers = max(0, round(forecast_result.final_prediction))

    hourly_distribution = distribute_covers_by_hour(total_covers)
    hourly_breakdown = [
        {"hour": slot.hour, "covers": slot.covers, "share": round(slot.share, 4)}
        for slot in hourly_distribution.slots
    ]

    staff_plan_result = StaffPlanningService(covers_by_hour=hourly_distribution.as_dict()).plan()
    staff_plan = [
        {
            "hour": h.hour,
            "covers": h.covers,
            "total_staff": h.total_staff(),
            "roles": [
                {"role": r.role, "covers_per_staff": r.covers_per_staff, "staff_required": r.staff_required}
                for r in h.roles
            ],
        }
        for h in staff_plan_result.hours
    ]

    ingredient_plan = []
    ingredient_plan_available = True
    ingredient_plan_error = None
    try:
        ingredient_result = IngredientForecastService.from_database(predicted_covers=total_covers).forecast()
        ingredient_plan = [
            {
                "name": item.name,
                "unit": item.unit,
                "base_quantity": item.base_quantity,
                "buffer_quantity": item.buffer_quantity,
                "total_quantity": item.total_quantity,
                "shelf_life_days": item.shelf_life_days,
                "supplier_lead_time_days": item.supplier_lead_time_days,
                "order_days_ahead": item.order_days_ahead,
                "freshness_risk": item.freshness_risk,
            }
            for item in ingredient_result.requirements
        ]
    except ValueError as exc:
        ingredient_plan_available = False
        ingredient_plan_error = str(exc)
        logger.warning("Ingredient forecast unavailable for %s: %s", target, exc)

    payload = {
        "date": target,
        "total_covers": total_covers,
        "hourly_breakdown": hourly_breakdown,
        "staff_plan": staff_plan,
        "ingredient_plan": ingredient_plan,
        "ingredient_plan_available": ingredient_plan_available,
        "ingredient_plan_error": ingredient_plan_error,
    }
    return dict(ForecastResponseSerializer(payload).data)
