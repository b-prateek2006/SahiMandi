from decimal import Decimal
import unittest

from app.capacity import (
    CapacityInputs,
    bounded_no_show_rate,
    calculate_bookable_qtl,
    calculate_capacity,
)


def make_inputs(**overrides: object) -> CapacityInputs:
    values: dict[str, object] = {
        "counters": 2,
        "rate_per_counter": Decimal("25"),
        "hours": 8,
        "bags_available": 3000,
        "qtl_per_bag": Decimal("0.4"),
        "hamalis": 6,
        "rate_per_hamali": Decimal("90"),
        "buffer_capacity": Decimal("2500"),
        "stock_open": Decimal("1800"),
        "trucks": 2,
        "trips_per_truck": 1,
        "qtl_per_truck": Decimal("250"),
    }
    values.update(overrides)
    return CapacityInputs(**values)  # type: ignore[arg-type]


class CapacityTests(unittest.TestCase):
    def test_worked_example_is_staff_bound(self) -> None:
        result = calculate_capacity(make_inputs())

        self.assertEqual(result.staff_cap, Decimal("400"))
        self.assertEqual(result.bag_cap, Decimal("1200.0"))
        self.assertEqual(result.hamali_cap, Decimal("540"))
        self.assertEqual(result.lift_today, Decimal("500"))
        self.assertEqual(result.yard_cap, Decimal("1200"))
        self.assertEqual(result.daily_capacity, Decimal("400"))
        self.assertEqual(result.binding_constraint, "STAFF")
        self.assertFalse(result.choked)

    def test_yard_shortfall_chokes_centre(self) -> None:
        result = calculate_capacity(make_inputs(trucks=0, stock_open=Decimal("2400")))

        self.assertEqual(result.yard_cap, Decimal("100"))
        self.assertEqual(result.daily_capacity, Decimal("100"))
        self.assertEqual(result.binding_constraint, "YARD")
        self.assertTrue(result.choked)

    def test_non_staff_constraint_is_not_choked_at_half_staff_or_more(self) -> None:
        result = calculate_capacity(make_inputs(bags_available=500))

        self.assertEqual(result.binding_constraint, "BAGS")
        self.assertEqual(result.daily_capacity, Decimal("200.0"))
        self.assertFalse(result.choked)

    def test_no_show_rate_uses_default_and_bounds(self) -> None:
        self.assertEqual(bounded_no_show_rate(None), Decimal("0.15"))
        self.assertEqual(bounded_no_show_rate(Decimal("0.01")), Decimal("0.05"))
        self.assertEqual(bounded_no_show_rate(Decimal("0.40")), Decimal("0.30"))

    def test_bookable_capacity_respects_one_point_two_five_ceiling(self) -> None:
        self.assertEqual(
            calculate_bookable_qtl(Decimal("400"), None),
            Decimal("470.5882352941176470588235294"),
        )
        self.assertEqual(calculate_bookable_qtl(Decimal("400"), Decimal("0.30")), Decimal("500.00"))
