"""Simulation module for 30-day season replay comparing Policy A (Baseline) vs Policy B (SahiMandi)."""

from decimal import Decimal
import math
import os
import random
import sys

# Ensure backend directory is accessible for importing capacity module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.capacity import CapacityInputs, calculate_bookable_qtl, calculate_capacity


def generate_harvest_curve(days: int = 30, total_season_qtl: float = 12000.0) -> list[float]:
    """Generate arrivals following a harvest curve: low initially, peak around days 10-18, then tailing off."""
    raw_weights = []
    for day in range(1, days + 1):
        # Sine-squared bell shape peaking between days 10 and 18
        weight = math.sin((day - 0.5) / days * math.pi) ** 2.2
        raw_weights.append(weight)
    
    sum_weights = sum(raw_weights)
    return [round((w / sum_weights) * total_season_qtl, 2) for w in raw_weights]


def run_simulation(days: int = 30, seed: int = 42) -> dict:
    """Run a 30-day season simulation comparing Policy A (Baseline) and Policy B (SahiMandi).

    Reuses the real capacity function calculate_capacity and calculate_bookable_qtl from app/capacity.py.
    """
    rng = random.Random(seed)
    arrivals = generate_harvest_curve(days=days)

    # Initial stock open set to 1800 quintals, initial bags stock set to 3000 bags (spec defaults)
    queue_a = 0.0
    stock_open_a = 1800.0
    bags_stock_a = 3000

    queue_b = 0.0
    stock_open_b = 1800.0
    bags_stock_b = 3000

    series_data = []
    total_redirected_farmers = 0

    for day_idx in range(days):
        day_num = day_idx + 1
        arr_qtl = arrivals[day_idx]

        # 20% of days have zero trucks
        trucks_today = 0 if rng.random() < 0.20 else rng.randint(2, 4)

        # Batch gunny bag deliveries with occasional gaps (every 6 days)
        if day_num in (6, 12, 18, 24):
            bags_stock_a += 2000
            bags_stock_b += 2000

        counters = 2
        rate_per_counter = Decimal("25")
        hours = 8
        hamalis = 6
        rate_per_hamali = Decimal("90")
        buffer_capacity = Decimal("2500")

        # --- Policy A (Baseline: Walk-ins, no booking cap, accept until yard full, then queue) ---
        inputs_a = CapacityInputs(
            counters=counters,
            rate_per_counter=rate_per_counter,
            hours=hours,
            bags_available=max(0, int(bags_stock_a)),
            qtl_per_bag=Decimal("0.4"),
            hamalis=hamalis,
            rate_per_hamali=rate_per_hamali,
            buffer_capacity=buffer_capacity,
            stock_open=Decimal(str(round(stock_open_a, 2))),
            trucks=trucks_today,
            trips_per_truck=1,
            qtl_per_truck=Decimal("250"),
        )
        res_a = calculate_capacity(inputs_a)
        cap_a = float(res_a.daily_capacity)

        total_grain_a = queue_a + arr_qtl
        processed_a = min(total_grain_a, cap_a)
        queue_a = max(0.0, total_grain_a - processed_a)

        lifted_a = float(res_a.lift_today)
        stock_open_a = max(0.0, stock_open_a + processed_a - lifted_a)
        bags_used_a = int(math.ceil(processed_a / 0.4))
        bags_stock_a = max(0, bags_stock_a - bags_used_a)

        staff_rate_a = float(res_a.staff_cap) / 8.0
        wait_h_a = round(queue_a / max(1.0, staff_rate_a), 2)

        # --- Policy B (SahiMandi: Bookings capped at bookable_qtl, redirect on choked) ---
        inputs_b = CapacityInputs(
            counters=counters,
            rate_per_counter=rate_per_counter,
            hours=hours,
            bags_available=max(0, int(bags_stock_b)),
            qtl_per_bag=Decimal("0.4"),
            hamalis=hamalis,
            rate_per_hamali=rate_per_hamali,
            buffer_capacity=buffer_capacity,
            stock_open=Decimal(str(round(stock_open_b, 2))),
            trucks=trucks_today,
            trips_per_truck=1,
            qtl_per_truck=Decimal("250"),
        )
        res_b = calculate_capacity(inputs_b)
        cap_b = float(res_b.daily_capacity)
        bookable_qtl_b = float(calculate_bookable_qtl(res_b.daily_capacity, Decimal("0.15")))

        redirected_qtl = 0.0
        if res_b.choked:
            redirect_ratio = 0.60
            redirected_qtl = arr_qtl * redirect_ratio
            redirected_farmers = max(1, int(math.ceil(redirected_qtl / 20.0)))
            total_redirected_farmers += redirected_farmers
        else:
            redirected_farmers = 0

        arriving_qtl_b = max(0.0, arr_qtl - redirected_qtl)
        # Cap bookings at bookable_qtl
        accepted_booking_qtl_b = min(arriving_qtl_b, bookable_qtl_b)

        total_grain_b = queue_b + accepted_booking_qtl_b
        processed_b = min(total_grain_b, cap_b)
        queue_b = max(0.0, total_grain_b - processed_b)

        lifted_b = float(res_b.lift_today)
        stock_open_b = max(0.0, stock_open_b + processed_b - lifted_b)
        bags_used_b = int(math.ceil(processed_b / 0.4))
        bags_stock_b = max(0, bags_stock_b - bags_used_b)

        staff_rate_b = float(res_b.staff_cap) / 8.0
        wait_h_b = round(queue_b / max(1.0, staff_rate_b), 2)

        series_data.append({
            "day": day_num,
            "arrivals_qtl": round(arr_qtl, 1),
            "queue_a": round(queue_a, 1),
            "queue_b": round(queue_b, 1),
            "wait_hours_a": wait_h_a,
            "wait_hours_b": wait_h_b,
            "redirected_farmers": redirected_farmers,
            "choked_a": res_a.choked,
            "choked_b": res_b.choked,
            "binding_a": res_a.binding_constraint,
            "binding_b": res_b.binding_constraint,
            "bookable_qtl_b": round(bookable_qtl_b, 1),
        })

    peak_queue_a = max(row["queue_a"] for row in series_data) or 1.0
    peak_queue_b = max(row["queue_b"] for row in series_data)
    peak_reduction_pct = round(((peak_queue_a - peak_queue_b) / peak_queue_a) * 100.0, 1)

    avg_wait_a = sum(row["wait_hours_a"] for row in series_data) / days
    avg_wait_b = sum(row["wait_hours_b"] for row in series_data) / days
    avg_wait_reduction_hours = round(max(0.0, avg_wait_a - avg_wait_b), 1)

    return {
        "days": days,
        "seed": seed,
        "series": series_data,
        "headline": {
            "peak_queue_reduction_pct": peak_reduction_pct,
            "avg_wait_reduction_hours": avg_wait_reduction_hours,
            "farmers_redirected_count": total_redirected_farmers,
            "peak_queue_a": round(peak_queue_a, 1),
            "peak_queue_b": round(peak_queue_b, 1),
            "avg_wait_a": round(avg_wait_a, 1),
            "avg_wait_b": round(avg_wait_b, 1),
        },
    }


if __name__ == "__main__":
    import json
    result = run_simulation()
    print(json.dumps(result["headline"], indent=2))
