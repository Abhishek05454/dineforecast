import logging
from datetime import date, timedelta

from celery import shared_task
from django.core.cache import cache
from django.conf import settings

from .cache import build_forecast_payload, forecast_cache_key

logger = logging.getLogger(__name__)

FORECAST_LOOKAHEAD_DAYS = 7


@shared_task
def recalculate_forecasts():
    today = date.today()
    succeeded = []
    failed = []

    for offset in range(1, FORECAST_LOOKAHEAD_DAYS + 1):
        target = today + timedelta(days=offset)
        try:
            serialized = build_forecast_payload(target)
            cache.set(forecast_cache_key(target), serialized, timeout=getattr(settings, "FORECAST_CACHE_TTL", 60 * 60 * 6))
            succeeded.append(str(target))
        except Exception as exc:
            logger.error("Failed to recalculate forecast for %s: %s", target, exc, exc_info=True)
            failed.append(str(target))

    logger.info(
        "Forecast recalculation complete. succeeded=%s failed=%s",
        succeeded,
        failed,
    )
    return {"succeeded": succeeded, "failed": failed}


@shared_task
def invalidate_forecast_cache(forecast_date: str):
    cache.delete(forecast_cache_key(date.fromisoformat(forecast_date)))
    logger.info("Invalidated forecast cache for %s", forecast_date)
