import logging
from datetime import date, timedelta

from celery import shared_task
from django.core.cache import cache

from .services import ForecastService

logger = logging.getLogger(__name__)

FORECAST_LOOKAHEAD_DAYS = 7


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def recalculate_forecasts(self):
    today = date.today()
    succeeded = []
    failed = []

    for offset in range(1, FORECAST_LOOKAHEAD_DAYS + 1):
        target = today + timedelta(days=offset)
        try:
            result = ForecastService(target_date=target).predict()
            cache_key = _forecast_cache_key(target)
            cache.set(cache_key, {
                "final_prediction": result.final_prediction,
                "base_prediction": result.base_prediction,
                "is_weekend": result.is_weekend,
                "weather": result.weather,
                "adjustments": result.adjustments,
                "last_7_days_avg": result.last_7_days_avg,
                "same_weekday_avg": result.same_weekday_avg,
                "recent_trend": result.recent_trend,
                "feedback_adjustment_factor": result.feedback_adjustment_factor,
                "feedback_samples": result.feedback_samples,
            })
            succeeded.append(str(target))
        except Exception as exc:
            logger.error("Failed to recalculate forecast for %s: %s", target, exc)
            failed.append(str(target))

    logger.info(
        "Forecast recalculation complete. succeeded=%s failed=%s",
        succeeded,
        failed,
    )
    return {"succeeded": succeeded, "failed": failed}


@shared_task
def invalidate_forecast_cache(forecast_date: str):
    cache.delete(_forecast_cache_key(date.fromisoformat(forecast_date)))
    logger.info("Invalidated forecast cache for %s", forecast_date)


def _forecast_cache_key(forecast_date: date) -> str:
    return f"forecast:{forecast_date.isoformat()}"
