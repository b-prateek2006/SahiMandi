from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.booking import allocate_first_fit, cancellation_releases_allowance
from app.models import Centre, Lot, Slot


class FakeSession:
    def __init__(self, slot=None, centre=None):
        self.slot = slot
        self.centre = centre
        self.added = []

    def get(self, model, identity):
        if model is Slot:
            return self.slot
        if model is Centre:
            return self.centre
        return None

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        return None


class BookingRuleTests(unittest.TestCase):
    def test_first_fit_does_not_allocate_beyond_hourly_allowance(self):
        first = Slot(id=1, hour=9, allowance_qtl=Decimal("20"), booked_qtl=Decimal("15"))
        second = Slot(id=2, hour=10, allowance_qtl=Decimal("20"), booked_qtl=Decimal("0"))

        self.assertIs(allocate_first_fit([second, first], Decimal("6")), second)
        self.assertIsNone(allocate_first_fit([first], Decimal("6")))

    def test_cancellation_releases_the_lot_allowance(self):
        slot = Slot(id=1, allowance_qtl=Decimal("50"), booked_qtl=Decimal("30"))
        lot = Lot(slot_id=1, declared_qtl=Decimal("12"), standby=False)

        cancellation_releases_allowance(FakeSession(slot=slot), lot)

        self.assertEqual(slot.booked_qtl, Decimal("18"))

    def test_choked_booking_rejects_and_returns_open_alternatives(self):
        from app.routers import bookings

        centre = Centre(id=1, active=True)
        fake_session = FakeSession(centre=centre)
        data = bookings.BookingInput(centre_id=1, date=date.today(), crop="Wheat", declared_qtl=Decimal("10"))
        choked = bookings.CentreAvailability(centre_id=1, date=date.today(), status="Choked", available_qtl=Decimal("0"), reason="Trucks unavailable, backlog 2400 quintals")
        alternative = bookings.CentreNearby(centre_id=2, name="Open Centre", district="Sehore", next_available_date=date.today(), distance_km=Decimal("4"), status="Open")

        with patch.object(bookings, "SessionLocal", return_value=fake_session), patch.object(bookings, "_farmer_id", return_value=9), patch.object(bookings, "_availability", return_value=choked), patch.object(bookings, "_alternatives", return_value=[alternative]):
            with self.assertRaises(HTTPException) as raised:
                bookings.create_booking(data, authorization="Bearer test")

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["alternatives"][0]["centre_id"], 2)


if __name__ == "__main__":
    unittest.main()
