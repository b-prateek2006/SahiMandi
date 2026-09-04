from datetime import date, datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.booking import release_missed_slots
from app.capacity import CapacityInputs, calculate_capacity
from app.models import Centre, Lot, Slot
from app.routers import bookings


class FakeSession:
    def __init__(self, centres=(), capacities=(), slots=(), lots=()):
        self.centres = {c.id: c for c in centres}
        self.capacities = {(cap.centre_id, cap.for_date): cap for cap in capacities}
        self.slots = list(slots)
        self.lots = list(lots)
        self.added = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, model, identity):
        if model is Centre:
            return self.centres.get(identity)
        if model is Slot:
            for slot in self.slots:
                if slot.id == identity:
                    return slot
        if model is Lot:
            for lot in self.lots:
                if lot.id == identity:
                    return lot
        return None

    def scalar(self, statement):
        statement_str = str(statement).lower()
        if "centre_daily_capacity" in statement_str:
            for cap in self.capacities.values():
                return cap
        if "lot" in statement_str:
            return self.lots[0] if self.lots else None
        return None

    def scalars(self, statement):
        try:
            entity = statement.column_descriptions[0].get("entity")
            if entity is Lot:
                return FakeResult(self.lots)
            if entity is Centre:
                return FakeResult(list(self.centres.values()))
            if entity is Slot:
                return FakeResult(self.slots)
        except Exception:
            pass
        statement_str = str(statement).lower()
        if "from lots" in statement_str:
            return FakeResult(self.lots)
        if "from centres" in statement_str:
            return FakeResult(list(self.centres.values()))
        if "from slots" in statement_str:
            return FakeResult(self.slots)
        return FakeResult([])

    def add(self, entity):
        self.added.append(entity)

    def add_all(self, entities):
        self.added.extend(entities)

    def commit(self):
        self.committed = True

    def flush(self):
        pass


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class ChokedAndRedirectTests(unittest.TestCase):
    def test_exact_choked_formula(self) -> None:
        """choked = (binding_constraint != 'STAFF') AND (daily_capacity < 0.5 * staff_cap)."""
        # Case 1: STAFF constraint -> never choked
        inputs_staff = CapacityInputs(
            counters=2, rate_per_counter=Decimal("25"), hours=8,
            bags_available=3000, qtl_per_bag=Decimal("0.4"),
            hamalis=6, rate_per_hamali=Decimal("90"),
            buffer_capacity=Decimal("2500"), stock_open=Decimal("1800"),
            trucks=2, trips_per_truck=1, qtl_per_truck=Decimal("250"),
        )
        res_staff = calculate_capacity(inputs_staff)
        self.assertEqual(res_staff.binding_constraint, "STAFF")
        self.assertFalse(res_staff.choked)

        # Case 2: YARD constraint with capacity 100 (< 0.5 * 400 = 200) -> choked
        inputs_choked = CapacityInputs(
            counters=2, rate_per_counter=Decimal("25"), hours=8,
            bags_available=3000, qtl_per_bag=Decimal("0.4"),
            hamalis=6, rate_per_hamali=Decimal("90"),
            buffer_capacity=Decimal("2500"), stock_open=Decimal("2400"),
            trucks=0, trips_per_truck=1, qtl_per_truck=Decimal("250"),
        )
        res_choked = calculate_capacity(inputs_choked)
        self.assertEqual(res_choked.binding_constraint, "YARD")
        self.assertEqual(res_choked.daily_capacity, Decimal("100"))
        self.assertTrue(res_choked.choked)

        # Case 3: BAGS constraint with capacity 250 (>= 0.5 * 400 = 200) -> NOT choked
        inputs_not_choked = CapacityInputs(
            counters=2, rate_per_counter=Decimal("25"), hours=8,
            bags_available=625, qtl_per_bag=Decimal("0.4"),
            hamalis=6, rate_per_hamali=Decimal("90"),
            buffer_capacity=Decimal("2500"), stock_open=Decimal("100"),
            trucks=2, trips_per_truck=1, qtl_per_truck=Decimal("250"),
        )
        res_not_choked = calculate_capacity(inputs_not_choked)
        self.assertEqual(res_not_choked.binding_constraint, "BAGS")
        self.assertEqual(res_not_choked.daily_capacity, Decimal("250.0"))
        self.assertFalse(res_not_choked.choked)

    def test_choked_centre_refuses_booking(self) -> None:
        """Booking a choked centre raises 409 Conflict with redirect alternatives."""
        centre = Centre(id=1, name="Choked Centre", district="Sehore", active=True)
        fake_session = FakeSession(centres=[centre])
        data = bookings.BookingInput(centre_id=1, date=date.today(), crop="Wheat", declared_qtl=Decimal("10"))
        choked_availability = bookings.CentreAvailability(
            centre_id=1, date=date.today(), status="Choked", available_qtl=Decimal("0"),
            reason="Trucks unavailable, backlog 2400 quintals",
        )
        alt = bookings.CentreNearby(
            centre_id=2, name="Open Centre", district="Sehore",
            next_available_date=date.today(), distance_km=Decimal("5.0"), status="Open",
        )

        with patch.object(bookings, "SessionLocal", return_value=fake_session), \
             patch.object(bookings, "_farmer_id", return_value=9), \
             patch.object(bookings, "_availability", return_value=choked_availability), \
             patch.object(bookings, "_alternatives", return_value=[alt]):
            with self.assertRaises(HTTPException) as ctx:
                bookings.create_booking(data, authorization="Bearer test")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["reason"], "Trucks unavailable, backlog 2400 quintals")
        self.assertEqual(len(ctx.exception.detail["alternatives"]), 1)
        self.assertEqual(ctx.exception.detail["alternatives"][0]["centre_id"], 2)

    def test_redirect_to_nearby_centre_with_actual_capacity(self) -> None:
        """_alternatives returns open centres sorted by distance, skipping choked ones."""
        today = date.today()
        c1 = Centre(id=1, name="Choked Origin", district="Sehore", latitude=Decimal("23.20"), longitude=Decimal("77.00"), active=True)
        c2 = Centre(id=2, name="Far Open", district="Sehore", latitude=Decimal("23.50"), longitude=Decimal("77.50"), active=True)
        c3 = Centre(id=3, name="Near Open", district="Sehore", latitude=Decimal("23.25"), longitude=Decimal("77.05"), active=True)
        c4 = Centre(id=4, name="Near Choked", district="Sehore", latitude=Decimal("23.21"), longitude=Decimal("77.01"), active=True)

        session = FakeSession(centres=[c1, c2, c3, c4])

        def mock_avail(sess, centre, for_date, qtl):
            if centre.id == 4:
                return bookings.CentreAvailability(centre_id=4, date=for_date, status="Choked", available_qtl=Decimal("0"))
            if centre.id in (2, 3):
                return bookings.CentreAvailability(centre_id=centre.id, date=for_date, status="Open", available_qtl=Decimal("100"))
            return bookings.CentreAvailability(centre_id=centre.id, date=for_date, status="Filling", available_qtl=Decimal("0"))

        with patch.object(bookings, "_availability", side_effect=mock_avail):
            results = bookings._alternatives(session, centre_id=1, for_date=today, qtl=Decimal("10"))

        # Should only include c3 (Near Open) and c2 (Far Open), in order of distance (c3 first)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].centre_id, 3)
        self.assertEqual(results[1].centre_id, 2)

    def test_no_suitable_alternative_behavior(self) -> None:
        """When no alternative centre has capacity, alternatives is empty list."""
        today = date.today()
        c1 = Centre(id=1, name="Origin", district="Sehore", active=True)
        c2 = Centre(id=2, name="All Choked 1", district="Sehore", active=True)
        c3 = Centre(id=3, name="All Choked 2", district="Sehore", active=True)

        session = FakeSession(centres=[c1, c2, c3])

        def mock_avail(sess, centre, for_date, qtl):
            return bookings.CentreAvailability(centre_id=centre.id, date=for_date, status="Choked", available_qtl=Decimal("0"))

        with patch.object(bookings, "_availability", side_effect=mock_avail):
            results = bookings._alternatives(session, centre_id=1, for_date=today, qtl=Decimal("10"))

        self.assertEqual(results, [])

    def test_next_date_fallback(self) -> None:
        """When requested date is full/choked at alternative, _alternatives finds the next open date."""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        c1 = Centre(id=1, name="Origin", district="Sehore", active=True)
        c2 = Centre(id=2, name="Tomorrow Open", district="Sehore", active=True)

        session = FakeSession(centres=[c1, c2])

        def mock_avail(sess, centre, for_date, qtl):
            if centre.id == 2 and for_date == tomorrow:
                return bookings.CentreAvailability(centre_id=2, date=tomorrow, status="Open", available_qtl=Decimal("100"))
            return bookings.CentreAvailability(centre_id=centre.id, date=for_date, status="Choked", available_qtl=Decimal("0"))

        with patch.object(bookings, "_availability", side_effect=mock_avail):
            results = bookings._alternatives(session, centre_id=1, for_date=today, qtl=Decimal("10"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].centre_id, 2)
        self.assertEqual(results[0].next_available_date, tomorrow)

    def test_standby_and_missed_slot_rules_remain_correct(self) -> None:
        """60-min grace period releases missed slot to standby without altering booking structure."""
        past_time = datetime(2026, 9, 4, 12, 0, 0)  # slot hour 9, now is 12:00 -> 3 hours past (> 60m)
        slot = Slot(id=1, centre_id=1, for_date=date(2026, 9, 4), hour=9, allowance_qtl=Decimal("50"), booked_qtl=Decimal("30"))
        lot = Lot(id=10, centre_id=1, slot_id=1, state="REGISTERED", standby=False, declared_qtl=Decimal("10"))

        session = FakeSession(slots=[slot], lots=[lot])

        release_missed_slots(session, centre_id=1, now=past_time)

        self.assertTrue(lot.standby)
        self.assertEqual(lot.state, "REGISTERED")
        self.assertEqual(slot.booked_qtl, Decimal("20"))


if __name__ == "__main__":
    unittest.main()
