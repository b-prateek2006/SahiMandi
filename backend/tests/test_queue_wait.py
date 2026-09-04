from datetime import datetime, timezone
from decimal import Decimal
import unittest

from app.models import Lot, LotEvent, ServiceTime
from app.queue_service import (
    DEFAULT_EWMA_SEED,
    calculate_estimated_wait,
    calculate_ewma_from_history,
    record_service_time,
)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, capacity=None, service_times=(), arrived_event=None):
        self.capacity = capacity
        self.service_times = list(service_times)
        self.arrived_event = arrived_event
        self.added = []

    def scalar(self, statement):
        statement_str = str(statement)
        if "centre_daily_capacity" in statement_str:
            return self.capacity
        if "lot_events" in statement_str:
            return self.arrived_event
        return None

    def scalars(self, statement):
        statement_str = str(statement)
        if "service_times" in statement_str:
            return FakeResult([st.minutes for st in self.service_times])
        return FakeResult([])

    def add(self, entity):
        self.added.append(entity)

    def flush(self):
        pass


class QueueWaitTests(unittest.TestCase):
    def test_first_observation_uses_12_minute_seed(self) -> None:
        """First observation uses 12-minute seed: ewma = 0.3 * latest + 0.7 * 12.0."""
        history = [20.0]
        ewma = calculate_ewma_from_history(history, seed=12.0, alpha=0.3)
        expected = 0.3 * 20.0 + 0.7 * 12.0  # 6.0 + 8.4 = 14.4
        self.assertAlmostEqual(ewma, expected, places=5)
        self.assertAlmostEqual(ewma, 14.4, places=5)

    def test_empty_history_returns_12_minute_seed(self) -> None:
        """A centre with no history defaults to 12 minutes seed."""
        ewma = calculate_ewma_from_history([], seed=12.0, alpha=0.3)
        self.assertEqual(ewma, 12.0)

    def test_ewma_update_with_alpha_0_3(self) -> None:
        """Subsequent EWMA updates maintain exponential decay with alpha = 0.3."""
        history = [20.0, 10.0]
        # Step 1: 0.3 * 20 + 0.7 * 12 = 14.4
        # Step 2: 0.3 * 10 + 0.7 * 14.4 = 3.0 + 10.08 = 13.08
        ewma = calculate_ewma_from_history(history, seed=12.0, alpha=0.3)
        self.assertAlmostEqual(ewma, 13.08, places=5)

    def test_queue_wait_calculation(self) -> None:
        """estimated_wait_minutes = (lots_ahead * ewma) / counters_open."""
        # 4 lots ahead, 15 minutes EWMA, 2 counters open
        wait = calculate_estimated_wait(lots_ahead=4, ewma=15.0, counters_open=2)
        self.assertEqual(wait, 30.0)

        # 3 lots ahead, 12 minutes EWMA, 1 counter open
        wait_1_counter = calculate_estimated_wait(lots_ahead=3, ewma=12.0, counters_open=1)
        self.assertEqual(wait_1_counter, 36.0)

    def test_zero_empty_queue_behavior(self) -> None:
        """Zero / empty queue returns 0.0 estimated wait minutes."""
        wait_zero = calculate_estimated_wait(lots_ahead=0, ewma=15.0, counters_open=2)
        self.assertEqual(wait_zero, 0.0)

        wait_negative = calculate_estimated_wait(lots_ahead=-1, ewma=15.0, counters_open=2)
        self.assertEqual(wait_negative, 0.0)

    def test_record_service_time_calculates_arrived_to_weighed_minutes(self) -> None:
        """On WEIGHED event, calculates minutes from ARRIVED timestamp and adds to service_times."""
        arrived_time = datetime(2026, 9, 4, 10, 0, 0, tzinfo=timezone.utc)
        weighed_time = datetime(2026, 9, 4, 10, 25, 30, tzinfo=timezone.utc)  # 25.5 minutes

        arrived_event = LotEvent(
            lot_id=1,
            to_state="ARRIVED",
            created_at=arrived_time,
        )
        session = FakeSession(arrived_event=arrived_event)
        lot = Lot(id=1, centre_id=5, state="ARRIVED")

        st = record_service_time(session, lot, weighed_at=weighed_time)

        self.assertIsNotNone(st)
        self.assertEqual(st.centre_id, 5)
        self.assertEqual(st.lot_id, 1)
        self.assertEqual(st.arrived_at, arrived_time)
        self.assertEqual(st.weighed_at, weighed_time)
        self.assertEqual(st.minutes, Decimal("25.5"))
        self.assertIn(st, session.added)


if __name__ == "__main__":
    unittest.main()
