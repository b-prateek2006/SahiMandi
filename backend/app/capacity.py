"""Deterministic, database-free procurement-centre capacity calculations."""

from dataclasses import dataclass
from decimal import Decimal


DEFAULT_NO_SHOW_RATE = Decimal("0.15")
MIN_NO_SHOW_RATE = Decimal("0.05")
MAX_NO_SHOW_RATE = Decimal("0.30")
OVERBOOKING_CEILING = Decimal("1.25")


@dataclass(frozen=True)
class CapacityInputs:
    counters: int
    rate_per_counter: Decimal
    hours: int
    bags_available: int
    qtl_per_bag: Decimal
    hamalis: int
    rate_per_hamali: Decimal
    buffer_capacity: Decimal
    stock_open: Decimal
    trucks: int
    trips_per_truck: int
    qtl_per_truck: Decimal


@dataclass(frozen=True)
class CapacityResult:
    staff_cap: Decimal
    bag_cap: Decimal
    hamali_cap: Decimal
    lift_today: Decimal
    yard_cap: Decimal
    daily_capacity: Decimal
    binding_constraint: str
    choked: bool


def calculate_capacity(inputs: CapacityInputs) -> CapacityResult:
    """Calculate the four physical constraints for one centre-day.

    The function deliberately has no database calls so it can be shared by the
    API and the season simulation.
    """
    staff_cap = Decimal(inputs.counters) * inputs.rate_per_counter * Decimal(inputs.hours)
    bag_cap = Decimal(inputs.bags_available) * inputs.qtl_per_bag
    hamali_cap = Decimal(inputs.hamalis) * inputs.rate_per_hamali
    lift_today = (
        Decimal(inputs.trucks)
        * Decimal(inputs.trips_per_truck)
        * inputs.qtl_per_truck
    )
    yard_cap = (inputs.buffer_capacity - inputs.stock_open) + lift_today

    constraints = (
        ("STAFF", staff_cap),
        ("BAGS", bag_cap),
        ("HAMALI", hamali_cap),
        ("YARD", yard_cap),
    )
    binding_constraint, daily_capacity = min(constraints, key=lambda item: item[1])
    choked = binding_constraint != "STAFF" and daily_capacity < Decimal("0.5") * staff_cap

    return CapacityResult(
        staff_cap=staff_cap,
        bag_cap=bag_cap,
        hamali_cap=hamali_cap,
        lift_today=lift_today,
        yard_cap=yard_cap,
        daily_capacity=daily_capacity,
        binding_constraint=binding_constraint,
        choked=choked,
    )


def bounded_no_show_rate(rate: Decimal | None) -> Decimal:
    """Apply the specified default and 5%--30% bounds to a centre's history."""
    if rate is None:
        return DEFAULT_NO_SHOW_RATE
    return min(MAX_NO_SHOW_RATE, max(MIN_NO_SHOW_RATE, rate))


def calculate_bookable_qtl(daily_capacity: Decimal, no_show_rate: Decimal | None) -> Decimal:
    """Return booking capacity after bounded no-show overbooking."""
    rate = bounded_no_show_rate(no_show_rate)
    return min(
        daily_capacity / (Decimal("1") - rate),
        OVERBOOKING_CEILING * daily_capacity,
    )
