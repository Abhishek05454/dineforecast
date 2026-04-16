# DineForecast

A restaurant resource planning system that forecasts daily covers, generates hourly staff plans, and projects ingredient orders — with a feedback-driven learning loop and an optional machine learning upgrade path.

---

## Problem Statement

Restaurant managers face three compounding planning problems every day:

1. **Demand uncertainty** — How many guests will arrive? Guessing wrong wastes staff hours or leaves tables understaffed.
2. **Staffing rigidity** — Role requirements (waiters, chefs, bartenders) differ per hour and scale with covers. Spreadsheet planning is slow and error-prone.
3. **Ingredient waste** — Ordering too much causes spoilage; too little causes 86s. Both hurt margin.

DineForecast automates all three using historical cover data, configurable role ratios, dish popularity, and a self-improving prediction engine.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        REST API                          │
│   GET /api/v1/forecasting/forecast/?date=YYYY-MM-DD      │
│   POST /api/v1/feedback/forecast/                        │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│                    Forecast Pipeline                     │
│                                                          │
│  ForecastService                                         │
│         │                                                │
│         └──── ForecastFeedbackService ◄──────────────    │
│                                                          │
│  StaffPlanningService                                    │
│  IngredientForecastService                               │
│                                                          │
│  MLForecastService is implemented as a standalone        │
│  service but is not wired into build_forecast_payload    │
│  or the forecast API. ForecastService is always used.    │
└──────────────┬───────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
  Redis Cache       PostgreSQL
  (6h TTL)         (HistoricalCover,
                    DishPopularity,
                    StaffRole, ...)
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│               Celery Beat (daily)                        │
│   recalculate_forecasts → pre-warms 7-day cache          │
└──────────────────────────────────────────────────────────┘
```

### Applications

| App | Responsibility |
|---|---|
| `apps.forecasting` | Cover prediction, hourly distribution, staff planning, ingredient forecasting |
| `apps.feedback` | Forecast accuracy recording, adaptive learning loop, guest feedback |
| `apps.operations` | Staff shift management, ingredient catalog, inventory tracking |
| `core` | Shared base models (UUID PK, timestamps), choices, exception handler |



---

## Forecasting Approach

### Rule-Based Engine (`ForecastService`)

The baseline engine combines three signals with configurable weights:

| Component | Default Weight | Description |
|---|---|---|
| `last_7` | 50% | Rolling 7-day average of daily covers |
| `weekday` | 30% | Same weekday average over 8 historical weeks |
| `trend` | 20% | Linear projection from the past 7 days |

One adjustment is applied on top:

- **Weekend** +30%

Weather adjustments (rain −15%, snow −30%) are implemented in `ForecastService` but the forecast API currently accepts only a `date` parameter and does not pass weather through, so these penalties are not active via the API path. They are available if `ForecastService` is called directly with a `weather` argument.

When fewer than 2 days of data exist for the trend, the component falls back to `last_7`. When a component has no data at all, its weight is redistributed proportionally to the remaining components.

### Machine Learning Engine (`MLForecastService`)

When ≥14 days of historical data are available, a `LinearRegression` model (scikit-learn) is trained on:

| Feature | Description |
|---|---|
| `day_of_week` | Integer 0–6 |
| `is_weekend` | Binary 0/1 |
| `past_covers` | 7-day rolling average at prediction time |

**Why weather is excluded:** `HistoricalCover` records are stored per `(date, hour)`. Weather can vary across hours in a day, making it unsuitable as a daily aggregate training feature without a dedicated per-day weather table. The forecast endpoint accepts only a `date` query parameter — `weather` is not a client-supplied field. Weather adjustments in the rule-based engine (rain −15%, snow −30%) are internal constants, not ML input features.

If scikit-learn is not installed or data is insufficient, the service falls back to `ForecastService` automatically.

### Feedback Learning Loop (`ForecastFeedbackService`)

After service, staff submit actual cover counts via `POST /api/v1/feedback/forecast/`. The system learns from errors over a rolling 30-day window:

```
maturity                   = min(1.0, sample_count / 10)
effective_lr               = 0.20 × maturity
mean_signed_error_fraction = mean signed percentage error as a fraction (e.g., 0.10 = +10%)
adjustment_factor          = clamp(1 + effective_lr × mean_signed_error_fraction, 0.70, 1.30)
```

The adjustment factor is multiplied into the final prediction. Component weights are also shifted — systematic underprediction increases the `trend` weight; overprediction decreases it — allowing the engine to self-correct its blend over time.

Submitting feedback immediately invalidates the Redis cache for that date.

### Hourly Distribution

Daily covers are distributed across service hours using the largest-remainder method, guaranteeing the sum of hourly integers equals the total exactly. The default distribution:

| Hour | Share |
|---|---|
| 12:00 | 10% |
| 13:00 | 25% |
| 14:00 | 20% |
| 19:00 | 20% |
| 20:00 | 15% |
| 21:00 | 10% |

### Staff Planning

For each hour, staff required per role = `ceil(covers / covers_per_staff)`. Roles and ratios are configured in `StaffRole` (database-driven, not hardcoded).

### Ingredient Forecasting

Projected orders per dish = `covers × (dish_popularity% / total_popularity%)`. Ingredient quantities are aggregated across dishes, then a buffer of 10–20% is added. A `freshness_risk` flag is raised when `supplier_lead_time_days > shelf_life_days`.

---

## API Reference

All endpoints require a JWT Bearer token in the `Authorization` header unless noted.

### Auth

The following endpoints are **unauthenticated** and are used to bootstrap JWT access:

- `POST /api/token/` — exchange valid user credentials for an access token and refresh token.
- `POST /api/token/refresh/` — exchange a valid refresh token for a new access token.

Create a local user with `python manage.py createsuperuser`, then call `POST /api/token/` to obtain tokens.

### Forecast

```
GET /api/v1/forecasting/forecast/?date=YYYY-MM-DD
```

Response:
```json
{
  "date": "2024-06-10",
  "total_covers": 240,
  "hourly_breakdown": [
    {"hour": 12, "covers": 24, "share": 0.1}
  ],
  "staff_plan": [
    {
      "hour": 12,
      "covers": 24,
      "total_staff": 3,
      "roles": [
        {"role": "waiter", "covers_per_staff": 20, "staff_required": 2}
      ]
    }
  ],
  "ingredient_plan": [
    {
      "name": "beef",
      "unit": "kg",
      "base_quantity": 12.0,
      "buffer_quantity": 1.8,
      "total_quantity": 13.8,
      "shelf_life_days": 3,
      "supplier_lead_time_days": 2,
      "order_days_ahead": 2,
      "freshness_risk": false
    }
  ],
  "ingredient_plan_available": true,
  "ingredient_plan_error": null
}
```

Responses are cached in Redis for 6 hours. A Celery beat job pre-warms the next 7 days every 24 hours.

### Feedback

```
POST /api/v1/feedback/forecast/
Content-Type: application/json

{"date": "2024-06-10", "predicted": 240, "actual": 265, "reason": "walk-ins"}
```

`date` is optional; if omitted it defaults to today. Returns 201 on create, 200 on update (upsert by date). Invalidates the forecast cache for that date.

---

## Infrastructure

| Concern | Choice | Notes |
|---|---|---|
| Database | PostgreSQL | `CONN_MAX_AGE=60`, connect timeout 10s |
| Cache | Redis via `django-redis` | `IGNORE_EXCEPTIONS=True` — cache miss degrades gracefully |
| Background tasks | Celery + Celery Beat | Daily forecast pre-warming; JSON serialization only |
| Auth | JWT (Simple JWT) | 60-min access tokens, 7-day refresh, token blacklist on rotation |
| WSGI | Gunicorn | Production server |
| Config | `python-decouple` | All secrets via environment variables |

---

## Project Structure

```
.                              # repo root (manage.py, conftest.py, requirements.txt live here)
├── apps/
│   ├── forecasting/
│   │   ├── models.py          # HistoricalCover, DemandForecast, StaffingRequirement, StaffRole, DishPopularity
│   │   ├── services.py        # ForecastService, MLForecastService, StaffPlanningService,
│   │   │                      # IngredientForecastService, distribute_covers_by_hour
│   │   ├── cache.py           # build_forecast_payload, forecast_cache_key
│   │   ├── views.py           # ForecastAPIView
│   │   ├── serializers.py
│   │   ├── tasks.py           # recalculate_forecasts, invalidate_forecast_cache
│   │   └── tests/
│   ├── feedback/
│   │   ├── models.py          # ForecastAccuracy, GuestFeedback, FeedbackResponse
│   │   ├── services.py        # ForecastFeedbackService
│   │   ├── views.py           # ForecastFeedbackAPIView
│   │   └── serializers.py
│   └── operations/
│       ├── models.py          # Shift, Ingredient, InventoryItem
│       └── views.py
├── core/
│   ├── models.py              # BaseModel (UUID PK + timestamps)
│   ├── choices.py             # StaffRoleChoices, UnitChoices
│   └── exceptions.py         # Custom DRF exception handler
├── config/
│   ├── settings.py
│   ├── urls.py
│   └── celery.py
└── conftest.py                # pytest autouse fixture (LocMemCache, cache.clear())
```

---

## Running Locally

**Prerequisites:** Python 3.12+, PostgreSQL, Redis, [Poetry](https://python-poetry.org/docs/#installation)

```bash
# 1. Install dependencies (Poetry creates and manages the virtualenv)
poetry install

# 2. Configure environment
cp .env.example .env   # set DB_NAME, DB_USER, DB_PASSWORD, SECRET_KEY

# 3. Migrate and run
poetry run python manage.py migrate
poetry run python manage.py runserver

# 4. Start Celery worker and beat (separate terminals)
poetry run celery -A config worker -l info
poetry run celery -A config beat -l info
```

**Run tests:**
```bash
poetry run pytest
```

---

## Design Tradeoffs

**Rule-based weights are hand-tuned, not learned.**
The 50/30/20 split between `last_7`, `weekday`, and `trend` is a starting assumption. The feedback loop shifts these weights over time, but the initial values encode a prior that may not match every restaurant's actual pattern. A fully data-driven approach would learn initial weights from a training set, but that requires more historical data upfront.

**ML model is retrained on every prediction.**
`MLForecastService` fits a new `LinearRegression` on each `predict()` call. This is simple and always uses the latest data, but becomes slower as history grows. A production system would train offline on a schedule and cache the model artefact.

**Weather is a per-hour field, not a per-day field.**
`HistoricalCover.weather` is stored at the hourly level, which is accurate but prevents using it as a daily ML training feature without ambiguity (what is the "weather" for a day with mixed conditions?). The ML model therefore omits weather. Adding a separate `DailyWeather` table would fix this and allow weather to become a proper feature.

**No model persistence.**
The fitted `LinearRegression` object is not saved between requests. Serialising the model to the database or filesystem (e.g., via `joblib`) would remove the per-request training overhead.

**Ingredient-dish mapping is a cross-product.**
`IngredientForecastService.from_database()` assigns every ingredient to every dish at a uniform quantity, because the schema has no per-dish recipe table. A `Recipe` model linking dishes to ingredients with specific quantities would make ingredient forecasting accurate per dish rather than uniform.

**Cache invalidation is coarse.**
Submitting feedback deletes the forecast for that date only. If the feedback learning loop shifts weights significantly, forecasts for adjacent dates may be stale. A broader invalidation strategy would be more conservative but more expensive.

---

## Future Improvements

**Data model**
- `DailyWeather` table — enables weather as an ML training feature
- `Recipe` model — per-dish ingredient quantities instead of a uniform cross-product
- `SpecialEvent` model — named events with expected cover multipliers, queryable by date range

**Forecasting**
- Offline model training with `joblib` serialisation — remove per-request fit overhead
- Feature engineering: school holidays, local events, month-of-year seasonality
- Confidence intervals — return a prediction range, not just a point estimate
- Multi-step lookahead — the Celery task already pre-warms 7 days; the model could be optimised for this horizon explicitly

**Operations**
- Shift auto-generation from staff plan — translate the hourly staff plan into concrete shift records
- Inventory reorder alerts — compare ingredient forecast against current inventory and flag shortfalls
- Waste tracking — compare ingredient orders to actual usage to refine buffer fractions

**Infrastructure**
- Model artefact caching in Redis — store fitted model as a compressed binary, invalidate when new training data arrives
- Prometheus metrics — expose prediction latency, cache hit rate, feedback sample count
- Async views — high-concurrency forecast endpoint could benefit from Django async + async ORM
- Staged rollout flag — allow `MLForecastService` to be toggled per-restaurant without a deploy

**Testing**
- Property-based tests (Hypothesis) for the hourly distribution allocator
- Load tests for the forecast endpoint under concurrent requests
- Contract tests for the API response shape against a schema registry
