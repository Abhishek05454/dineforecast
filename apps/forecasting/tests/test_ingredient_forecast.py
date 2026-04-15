import pytest

from apps.forecasting.models import DishPopularity
from apps.forecasting.services import (
    DEFAULT_BUFFER_FRACTION,
    IngredientForecastService,
    IngredientPerDishInput,
)
from apps.operations.models import Ingredient


def _make_dish(name: str, popularity_pct: float):
    DishPopularity.objects.update_or_create(
        dish_name=name,
        defaults={"average_orders_percentage": popularity_pct},
    )


def _make_ingredient(name: str, qty_per_dish: float, shelf_life: int, lead_time: int, unit: str = "kg"):
    Ingredient.objects.update_or_create(
        name=name,
        defaults={
            "default_quantity_per_dish": qty_per_dish,
            "shelf_life_days": shelf_life,
            "supplier_lead_time_days": lead_time,
            "unit": unit,
        },
    )


class TestIngredientForecastService:
    def test_aggregates_requirements_across_dishes_with_per_dish_quantities(self):
        result = IngredientForecastService(
            predicted_covers=100,
            dish_popularity={"burger": 60.0, "pasta": 40.0},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "beef", 0.2, "kg", 3, 2),
                IngredientPerDishInput("pasta", "beef", 0.1, "kg", 3, 2),
            ],
            buffer_fraction=0.15,
        ).forecast()

        req = result.requirements[0]
        assert req.name == "beef"
        assert req.base_quantity == 16.0
        assert req.buffer_quantity == 2.4
        assert req.total_quantity == 18.4

    def test_scales_for_multiple_ingredients(self):
        result = IngredientForecastService(
            predicted_covers=100,
            dish_popularity={"burger": 60.0, "pasta": 40.0},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "beef", 0.2, "kg", 3, 2),
                IngredientPerDishInput("pasta", "beef", 0.1, "kg", 3, 2),
                IngredientPerDishInput("burger", "cheese", 0.05, "kg", 10, 4),
                IngredientPerDishInput("pasta", "cheese", 0.08, "kg", 10, 4),
            ],
        ).forecast()

        by_name = {r.name: r for r in result.requirements}
        assert by_name["beef"].base_quantity == 16.0
        assert by_name["cheese"].base_quantity == 6.2

    def test_normalizes_popularity_even_when_not_100(self):
        result = IngredientForecastService(
            predicted_covers=80,
            dish_popularity={"burger": 3, "pasta": 1},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "salt", 0.01, "kg", 365, 7),
                IngredientPerDishInput("pasta", "salt", 0.01, "kg", 365, 7),
            ],
        ).forecast()

        # 80 covers split 75/25 -> (60 * 0.01) + (20 * 0.01) = 0.8
        assert result.requirements[0].base_quantity == 0.8

    def test_recipe_line_with_unknown_dish_contributes_zero(self):
        result = IngredientForecastService(
            predicted_covers=100,
            dish_popularity={"burger": 100},
            ingredient_per_dish=[
                IngredientPerDishInput("unknown", "spice", 0.02, "kg", 120, 5),
            ],
        ).forecast()

        assert result.requirements[0].base_quantity == 0.0

    def test_zero_covers_yields_zero_quantities(self):
        result = IngredientForecastService(
            predicted_covers=0,
            dish_popularity={"burger": 100},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "beef", 0.2, "kg", 3, 2),
            ],
        ).forecast()

        req = result.requirements[0]
        assert req.base_quantity == 0.0
        assert req.total_quantity == 0.0

    def test_no_ingredients_returns_empty_requirements(self):
        result = IngredientForecastService(predicted_covers=100, dish_popularity={"burger": 100}).forecast()
        assert result.requirements == []

    def test_as_dict_returns_name_to_total_quantity(self):
        result = IngredientForecastService(
            predicted_covers=100,
            dish_popularity={"burger": 100},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "beef", 0.2, "kg", 3, 2),
            ],
        ).forecast()
        mapping = result.as_dict()
        assert "beef" in mapping
        assert mapping["beef"] == round(20.0 * (1 + DEFAULT_BUFFER_FRACTION), 4)

    def test_result_stores_covers_and_buffer_fraction(self):
        result = IngredientForecastService(predicted_covers=200, buffer_fraction=0.10).forecast()
        assert result.covers == 200
        assert result.buffer_fraction == 0.10


class TestOrderDaysAhead:
    def test_order_days_ahead_is_supplier_lead_time(self):
        result = IngredientForecastService(
            predicted_covers=10,
            dish_popularity={"burger": 100},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "beef", 0.2, "kg", 5, 2),
            ],
        ).forecast()
        assert result.requirements[0].order_days_ahead == 2

    def test_sets_freshness_risk_when_lead_time_exceeds_shelf_life(self):
        result = IngredientForecastService(
            predicted_covers=10,
            dish_popularity={"burger": 100},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "greens", 0.2, "kg", 2, 5),
            ],
        ).forecast()
        assert result.requirements[0].freshness_risk is True

    def test_no_freshness_risk_when_shelf_life_covers_lead_time(self):
        result = IngredientForecastService(
            predicted_covers=10,
            dish_popularity={"burger": 100},
            ingredient_per_dish=[
                IngredientPerDishInput("burger", "oil", 0.05, "kg", 30, 7),
            ],
        ).forecast()
        assert result.requirements[0].freshness_risk is False


@pytest.mark.django_db
class TestFromDatabaseFactory:
    def test_raises_when_no_dish_popularity_in_db(self):
        with pytest.raises(ValueError, match="No DishPopularity rows"):
            IngredientForecastService.from_database(predicted_covers=100)

    def test_builds_service_from_existing_models(self):
        _make_dish("burger", 100.0)
        _make_ingredient("beef", qty_per_dish=0.2, shelf_life=3, lead_time=2)

        result = IngredientForecastService.from_database(predicted_covers=100).forecast()

        assert result.requirements
        assert result.requirements[0].name == "beef"
        assert result.requirements[0].total_quantity == round(
            20.0 * (1 + DEFAULT_BUFFER_FRACTION),
            4,
        )


class TestIngredientForecastServiceValidation:
    def test_raises_on_negative_covers(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            IngredientForecastService(predicted_covers=-1)

    def test_raises_on_nan_covers(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            IngredientForecastService(predicted_covers=float("nan"))

    def test_raises_on_buffer_below_minimum(self):
        with pytest.raises(ValueError, match="0.10 and 0.20"):
            IngredientForecastService(predicted_covers=100, buffer_fraction=0.05)

    def test_raises_on_buffer_above_maximum(self):
        with pytest.raises(ValueError, match="0.10 and 0.20"):
            IngredientForecastService(predicted_covers=100, buffer_fraction=0.25)

    def test_boundary_buffer_10_percent_valid(self):
        svc = IngredientForecastService(predicted_covers=100, buffer_fraction=0.10)
        assert svc.buffer_fraction == 0.10

    def test_boundary_buffer_20_percent_valid(self):
        svc = IngredientForecastService(predicted_covers=100, buffer_fraction=0.20)
        assert svc.buffer_fraction == 0.20

    def test_default_buffer_is_15_percent(self):
        svc = IngredientForecastService(predicted_covers=100)
        assert svc.buffer_fraction == DEFAULT_BUFFER_FRACTION
        assert DEFAULT_BUFFER_FRACTION == 0.15

    def test_raises_on_invalid_popularity_value(self):
        with pytest.raises(ValueError, match="Dish popularity"):
            IngredientForecastService(predicted_covers=100, dish_popularity={"burger": -5})

    def test_raises_on_invalid_recipe_quantity(self):
        with pytest.raises(ValueError, match="quantity_per_dish"):
            IngredientForecastService(
                predicted_covers=100,
                dish_popularity={"burger": 100},
                ingredient_per_dish=[
                    IngredientPerDishInput("burger", "beef", -0.1, "kg", 3, 2),
                ],
            )

    def test_raises_on_inconsistent_ingredient_metadata(self):
        with pytest.raises(ValueError, match="consistent"):
            IngredientForecastService(
                predicted_covers=100,
                dish_popularity={"burger": 60, "pasta": 40},
                ingredient_per_dish=[
                    IngredientPerDishInput("burger", "salt", 0.01, "kg", 365, 7),
                    IngredientPerDishInput("pasta", "salt", 0.02, "litre", 365, 7),
                ],
            )

    def test_raises_on_empty_unit(self):
        with pytest.raises(ValueError, match="unit must be a non-empty string"):
            IngredientForecastService(
                predicted_covers=100,
                dish_popularity={"burger": 100},
                ingredient_per_dish=[
                    IngredientPerDishInput("burger", "beef", 0.2, "", 3, 2),
                ],
            )

    def test_raises_on_bool_shelf_life_days(self):
        with pytest.raises(ValueError, match="plain integers"):
            IngredientForecastService(
                predicted_covers=100,
                dish_popularity={"burger": 100},
                ingredient_per_dish=[
                    IngredientPerDishInput("burger", "beef", 0.2, "kg", True, 2),
                ],
            )

    def test_raises_on_negative_shelf_life_days(self):
        with pytest.raises(ValueError, match="non-negative"):
            IngredientForecastService(
                predicted_covers=100,
                dish_popularity={"burger": 100},
                ingredient_per_dish=[
                    IngredientPerDishInput("burger", "beef", 0.2, "kg", -1, 2),
                ],
            )
