import pytest

from apps.forecasting.services import (
    DEFAULT_HOURLY_DISTRIBUTION,
    HourlyDistributionResult,
    distribute_covers_by_hour,
)


class TestDistributeCoversByHour:
    def test_default_distribution_returns_correct_hours(self):
        result = distribute_covers_by_hour(100)
        hours = [slot.hour for slot in result.slots]
        assert hours == sorted(DEFAULT_HOURLY_DISTRIBUTION.keys())

    def test_covers_are_distributed_proportionally(self):
        result = distribute_covers_by_hour(100)
        slot_13 = next(s for s in result.slots if s.hour == 13)
        assert slot_13.covers == 25  # 100 * 0.25

    def test_slots_are_sorted_by_hour(self):
        custom = {19: 0.5, 12: 0.3, 14: 0.2}
        result = distribute_covers_by_hour(100, distribution=custom)
        assert [s.hour for s in result.slots] == [12, 14, 19]

    def test_as_dict_returns_hour_to_covers_map(self):
        result = distribute_covers_by_hour(100)
        mapping = result.as_dict()
        assert isinstance(mapping, dict)
        assert mapping[13] == 25
        assert mapping[12] == 10

    def test_total_covers_stored_on_result(self):
        result = distribute_covers_by_hour(200)
        assert result.total_covers == 200

    def test_custom_distribution(self):
        custom = {9: 0.4, 10: 0.6}
        result = distribute_covers_by_hour(50, distribution=custom)
        assert result.as_dict() == {9: 20, 10: 30}

    def test_slot_covers_sum_to_total(self):
        # Independent rounding can cause sum != total; largest-remainder must fix this
        custom = {12: 0.333, 13: 0.333, 14: 0.334}
        result = distribute_covers_by_hour(10, distribution=custom)
        assert sum(s.covers for s in result.slots) == round(result.total_covers)

    def test_slot_covers_sum_to_total_with_equal_shares(self):
        # 0.5 / 0.5 with total=1 — banker's rounding yields 0+0 without largest-remainder
        result = distribute_covers_by_hour(1, distribution={12: 0.5, 13: 0.5})
        assert sum(s.covers for s in result.slots) == 1

    def test_fractional_covers_are_integers(self):
        custom = {12: 0.333, 13: 0.333, 14: 0.334}
        result = distribute_covers_by_hour(10, distribution=custom)
        for slot in result.slots:
            assert isinstance(slot.covers, int)


class TestValidateDistribution:
    def test_raises_when_shares_sum_below_1(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            distribute_covers_by_hour(100, distribution={12: 0.4, 13: 0.4})

    def test_raises_when_shares_sum_above_1(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            distribute_covers_by_hour(100, distribution={12: 0.6, 13: 0.6})

    def test_allows_tolerance_of_0_01(self):
        # 0.999 is within ±0.01 — should not raise
        result = distribute_covers_by_hour(100, distribution={12: 0.5, 13: 0.499})
        assert result is not None

    def test_raises_when_hour_out_of_range(self):
        with pytest.raises(ValueError, match="out of range"):
            distribute_covers_by_hour(100, distribution={25: 0.5, 13: 0.5})

    def test_raises_on_negative_share(self):
        with pytest.raises(ValueError, match="non-negative"):
            distribute_covers_by_hour(100, distribution={12: 1.2, 13: -0.2})

    def test_raises_on_empty_distribution(self):
        with pytest.raises(ValueError, match="empty"):
            distribute_covers_by_hour(100, distribution={})
