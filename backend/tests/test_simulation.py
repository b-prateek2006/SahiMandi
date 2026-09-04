from decimal import Decimal
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.capacity import CapacityInputs, calculate_bookable_qtl, calculate_capacity
from sim.run_simulation import generate_harvest_curve, run_simulation


class SimulationTests(unittest.TestCase):
    def test_same_seed_produces_identical_results(self) -> None:
        """Deterministic simulation: identical seed produces identical output."""
        run1 = run_simulation(days=30, seed=42)
        run2 = run_simulation(days=30, seed=42)

        self.assertEqual(run1["headline"], run2["headline"])
        self.assertEqual(run1["series"], run2["series"])

    def test_30_day_simulation_execution(self) -> None:
        """Simulation produces 30 daily series points when days=30."""
        res = run_simulation(days=30, seed=42)
        self.assertEqual(res["days"], 30)
        self.assertEqual(len(res["series"]), 30)
        self.assertEqual([row["day"] for row in res["series"]], list(range(1, 31)))

    def test_harvest_curve_peaks_around_days_10_to_18(self) -> None:
        """Harvest curve is low initially, rises to a peak around days 10-18, then tails off."""
        curve = generate_harvest_curve(days=30)
        self.assertEqual(len(curve), 30)

        early_avg = sum(curve[:5]) / 5
        peak_avg = sum(curve[9:18]) / 9
        late_avg = sum(curve[25:]) / 5

        self.assertGreater(peak_avg, early_avg)
        self.assertGreater(peak_avg, late_avg)

    def test_policy_a_vs_policy_b_behavior(self) -> None:
        """Policy A does not cap bookings; Policy B caps bookings at bookable_qtl and redirects on choked days."""
        res = run_simulation(days=30, seed=42)
        series = res["series"]

        choked_days = [row for row in series if row["choked_b"]]
        self.assertGreater(len(choked_days), 0)

        for row in choked_days:
            self.assertGreater(row["redirected_farmers"], 0)

        # Confirm Policy B maintains significantly lower queue and wait times during season peak
        peak_day = max(series, key=lambda row: row["arrivals_qtl"])
        self.assertGreater(peak_day["queue_a"], peak_day["queue_b"])
        self.assertGreater(peak_day["wait_hours_a"], peak_day["wait_hours_b"])

    def test_reuses_real_capacity_engine(self) -> None:
        """Verify capacity engine functions are callable and imported from app.capacity."""
        inputs = CapacityInputs(
            counters=2, rate_per_counter=Decimal("25"), hours=8, bags_available=3000,
            qtl_per_bag=Decimal("0.4"), hamalis=6, rate_per_hamali=Decimal("90"),
            buffer_capacity=Decimal("2500"), stock_open=Decimal("1800"),
            trucks=2, trips_per_truck=1, qtl_per_truck=Decimal("250"),
        )
        res = calculate_capacity(inputs)
        bookable = calculate_bookable_qtl(res.daily_capacity, None)
        self.assertEqual(res.binding_constraint, "STAFF")
        self.assertIsNotNone(bookable)

    def test_headline_metrics_calculated_from_series(self) -> None:
        """Headline metrics are derived directly from the generated simulation series."""
        res = run_simulation(days=30, seed=42)
        headline = res["headline"]

        self.assertIn("peak_queue_reduction_pct", headline)
        self.assertIn("avg_wait_reduction_hours", headline)
        self.assertIn("farmers_redirected_count", headline)

        self.assertGreater(headline["peak_queue_reduction_pct"], 0.0)
        self.assertGreater(headline["avg_wait_reduction_hours"], 0.0)
        self.assertGreater(headline["farmers_redirected_count"], 0)


if __name__ == "__main__":
    unittest.main()
