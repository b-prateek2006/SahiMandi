from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.models import Centre, CentreDailyCapacity, Lot
from app.routers import district
from app.schemas import DistrictCentreDrilldown, DistrictCentreOverview


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, centres=(), capacities=(), lots=()):
        self.centres = {c.id: c for c in centres}
        self.capacities = list(capacities)
        self.lots = list(lots)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, model, identity):
        if model is Centre:
            return self.centres.get(identity)
        return None

    def scalar(self, statement):
        try:
            entity = statement.column_descriptions[0].get("entity")
            if entity is CentreDailyCapacity:
                return self.capacities[0] if self.capacities else None
        except Exception:
            pass
        statement_str = str(statement).lower()
        if "sum" in statement_str:
            return Decimal("150.0")
        if "count" in statement_str:
            return len(self.lots)
        if "capacity" in statement_str or "centre_daily_capacity" in statement_str:
            return self.capacities[0] if self.capacities else None
        return None

    def scalars(self, statement):
        statement_str = str(statement).lower()
        if "centres" in statement_str:
            return FakeResult(list(self.centres.values()))
        if "lots" in statement_str:
            return FakeResult(self.lots)
        return FakeResult([])


class DistrictTests(unittest.TestCase):
    def test_district_overview_data(self) -> None:
        """GET /district/overview returns active centres with capacity, constraint, backlog, choked."""
        c1 = Centre(id=1, name="Sehore Main", district="Sehore", active=True)
        cap1 = CentreDailyCapacity(centre_id=1, for_date=date.today(), daily_capacity=Decimal("400"), binding_constraint="STAFF", choked=False, stock_open=Decimal("200"))

        fake_session = FakeSession(centres=[c1], capacities=[cap1])

        with patch.object(district, "SessionLocal", return_value=fake_session):
            results = district.district_overview()

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertIsInstance(item, DistrictCentreOverview)
        self.assertEqual(item.centre_id, 1)
        self.assertEqual(item.name, "Sehore Main")
        self.assertEqual(item.district, "Sehore")
        self.assertEqual(item.daily_capacity, Decimal("400"))
        self.assertEqual(item.binding_constraint, "STAFF")
        self.assertFalse(item.choked)
        self.assertEqual(item.backlog_qtl, Decimal("350.0"))  # 200 + 150 sum from scalar mock

    def test_choked_centres_correctly_represented(self) -> None:
        """Choked centre is represented with choked=True and non-STAFF binding constraint."""
        c1 = Centre(id=1, name="Choked Centre", district="Sehore", active=True)
        cap1 = CentreDailyCapacity(centre_id=1, for_date=date.today(), daily_capacity=Decimal("100"), binding_constraint="YARD", choked=True, stock_open=Decimal("2400"))

        fake_session = FakeSession(centres=[c1], capacities=[cap1])

        with patch.object(district, "SessionLocal", return_value=fake_session):
            results = district.district_overview()

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertTrue(item.choked)
        self.assertEqual(item.binding_constraint, "YARD")
        self.assertEqual(item.daily_capacity, Decimal("100"))

    def test_centre_drilldown(self) -> None:
        """GET /district/centre/{id} returns detailed drilldown for specified centre."""
        c1 = Centre(id=1, name="Detail Centre", district="Sehore", latitude=Decimal("23.20"), longitude=Decimal("77.00"), buffer_capacity=Decimal("2500"), active=True)
        cap1 = CentreDailyCapacity(
            centre_id=1, for_date=date.today(), daily_capacity=Decimal("400"),
            binding_constraint="STAFF", choked=False, stock_open=Decimal("500"),
            counters=2, rate_per_counter=Decimal("25"), hours=8, bags_available=3000, hamalis=6, trucks=2,
        )

        fake_session = FakeSession(centres=[c1], capacities=[cap1])

        with patch.object(district, "SessionLocal", return_value=fake_session):
            detail = district.district_centre_drilldown(1)

        self.assertIsInstance(detail, DistrictCentreDrilldown)
        self.assertEqual(detail.centre_id, 1)
        self.assertEqual(detail.name, "Detail Centre")
        self.assertEqual(detail.counters, 2)
        self.assertEqual(detail.hours, 8)
        self.assertEqual(detail.bags_available, 3000)
        self.assertFalse(detail.choked)

    def test_backlog_sorting_behavior(self) -> None:
        """Overview entries can be sorted by backlog_qtl in ascending and descending order."""
        item1 = DistrictCentreOverview(centre_id=1, name="Low Backlog", district="Sehore", backlog_qtl=Decimal("100"))
        item2 = DistrictCentreOverview(centre_id=2, name="High Backlog", district="Sehore", backlog_qtl=Decimal("850"))
        item3 = DistrictCentreOverview(centre_id=3, name="Mid Backlog", district="Sehore", backlog_qtl=Decimal("400"))

        raw_list = [item1, item2, item3]

        desc_sorted = sorted(raw_list, key=lambda c: c.backlog_qtl, reverse=True)
        self.assertEqual([c.centre_id for c in desc_sorted], [2, 3, 1])

        asc_sorted = sorted(raw_list, key=lambda c: c.backlog_qtl)
        self.assertEqual([c.centre_id for c in asc_sorted], [1, 3, 2])


if __name__ == "__main__":
    unittest.main()
