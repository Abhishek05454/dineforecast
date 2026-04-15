import pytest

from apps.forecasting.models import StaffRole
from apps.forecasting.services import StaffPlanningService


def _make_role(role: str, covers_per_staff: int):
    StaffRole.objects.get_or_create(role=role, defaults={"covers_per_staff": covers_per_staff})


# ---------------------------------------------------------------------------
# Core planning logic
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStaffPlanningService:
    def test_staff_required_rounds_up(self):
        _make_role("waiter", 10)
        result = StaffPlanningService({12: 25}).plan()
        slot = result.hours[0]
        waiter = next(r for r in slot.roles if r.role == "waiter")
        assert waiter.staff_required == 3  # ceil(25/10)

    def test_zero_covers_requires_zero_staff(self):
        _make_role("waiter", 10)
        result = StaffPlanningService({12: 0}).plan()
        slot = result.hours[0]
        assert all(r.staff_required == 0 for r in slot.roles)

    def test_exact_division_no_rounding(self):
        _make_role("chef", 5)
        result = StaffPlanningService({19: 20}).plan()
        chef = next(r for r in result.hours[0].roles if r.role == "chef")
        assert chef.staff_required == 4

    def test_multiple_roles_each_computed_independently(self):
        _make_role("waiter", 10)
        _make_role("chef", 5)
        result = StaffPlanningService({12: 20}).plan()
        slot = result.hours[0]
        by_role = {r.role: r.staff_required for r in slot.roles}
        assert by_role["waiter"] == 2   # ceil(20/10)
        assert by_role["chef"] == 4     # ceil(20/5)

    def test_hours_sorted_ascending(self):
        _make_role("waiter", 10)
        result = StaffPlanningService({21: 10, 12: 20, 19: 15}).plan()
        assert [h.hour for h in result.hours] == [12, 19, 21]

    def test_total_staff_sums_all_roles(self):
        _make_role("waiter", 10)
        _make_role("chef", 5)
        result = StaffPlanningService({12: 20}).plan()
        assert result.hours[0].total_staff() == 6  # 2 waiters + 4 chefs

    def test_as_dict_shape(self):
        _make_role("waiter", 10)
        result = StaffPlanningService({12: 10, 13: 20}).plan()
        mapping = result.as_dict()
        assert set(mapping.keys()) == {12, 13}
        assert mapping[12]["waiter"] == 1
        assert mapping[13]["waiter"] == 2

    def test_role_requirement_stores_covers_per_staff(self):
        _make_role("bartender", 8)
        result = StaffPlanningService({20: 16}).plan()
        bartender = next(r for r in result.hours[0].roles if r.role == "bartender")
        assert bartender.covers_per_staff == 8

    def test_covers_stored_on_hourly_slot(self):
        _make_role("waiter", 10)
        result = StaffPlanningService({14: 33}).plan()
        assert result.hours[0].covers == 33

    def test_no_roles_in_db_returns_empty_role_lists(self):
        result = StaffPlanningService({12: 50}).plan()
        assert result.hours[0].roles == []

    def test_role_with_zero_covers_per_staff_is_excluded(self):
        StaffRole.objects.get_or_create(role="cashier", defaults={"covers_per_staff": 0})
        _make_role("waiter", 10)
        result = StaffPlanningService({12: 20}).plan()
        roles_in_result = [r.role for r in result.hours[0].roles]
        assert "cashier" not in roles_in_result
        assert "waiter" in roles_in_result


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestStaffPlanningServiceValidation:
    def test_raises_on_empty_input(self):
        with pytest.raises(ValueError, match="must not be empty"):
            StaffPlanningService({})

    def test_raises_on_bool_hour_key(self):
        with pytest.raises(ValueError, match="plain integers"):
            StaffPlanningService({True: 10})

    def test_raises_on_float_hour_key(self):
        with pytest.raises(ValueError, match="plain integers"):
            StaffPlanningService({12.5: 10})

    def test_raises_on_hour_out_of_range(self):
        with pytest.raises(ValueError, match="range 0-23"):
            StaffPlanningService({25: 10})

    def test_raises_on_string_cover_value(self):
        with pytest.raises(ValueError, match="plain integers"):
            StaffPlanningService({12: "10"})

    def test_raises_on_bool_cover_value(self):
        with pytest.raises(ValueError, match="plain integers"):
            StaffPlanningService({12: True})

    def test_raises_on_negative_covers(self):
        with pytest.raises(ValueError, match="non-negative"):
            StaffPlanningService({12: -5})
