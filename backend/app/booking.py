"""Slot allocation and missed-slot rules shared by farmer booking endpoints."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capacity import calculate_bookable_qtl
from app.models import CentreDailyCapacity, Lot, Slot


def hourly_allowance(bookable_qtl: Decimal, hours: int) -> Decimal:
    return bookable_qtl / Decimal(hours)


def allocate_first_fit(slots: list[Slot], declared_qtl: Decimal) -> Slot | None:
    """Return the earliest slot with enough remaining hourly allowance."""
    for slot in sorted(slots, key=lambda candidate: candidate.hour):
        booked = slot.booked_qtl or Decimal("0")
        allowance = slot.allowance_qtl or Decimal("0")
        if allowance - booked >= declared_qtl:
            return slot
    return None


def no_show_rate(session: Session, centre_id: int, for_date: date) -> Decimal | None:
    start = for_date - timedelta(days=14)
    booked_count, missed_count = 0, 0
    lots = session.scalars(
        select(Lot).join(Slot, Lot.slot_id == Slot.id).where(
            Lot.centre_id == centre_id,
            Slot.for_date >= start,
            Slot.for_date < for_date,
        )
    ).all()
    for lot in lots:
        booked_count += 1
        if lot.standby:
            missed_count += 1
    if not booked_count:
        return None
    return Decimal(missed_count) / Decimal(booked_count)


def slots_for_capacity(
    session: Session,
    capacity: CentreDailyCapacity,
    open_hour: int,
) -> list[Slot]:
    """Create or return a date's hourly buckets using its stored capacity."""
    existing = session.scalars(
        select(Slot).where(
            Slot.centre_id == capacity.centre_id,
            Slot.for_date == capacity.for_date,
        ).order_by(Slot.hour)
    ).all()
    if existing:
        return existing

    rate = no_show_rate(session, capacity.centre_id, capacity.for_date)
    bookable = calculate_bookable_qtl(capacity.daily_capacity or Decimal("0"), rate)
    allowance = hourly_allowance(bookable, capacity.hours or 0)
    slots = [
        Slot(
            centre_id=capacity.centre_id,
            for_date=capacity.for_date,
            hour=open_hour + offset,
            allowance_qtl=allowance,
            booked_qtl=Decimal("0"),
        )
        for offset in range(capacity.hours or 0)
    ]
    session.add_all(slots)
    session.flush()
    return slots


def release_missed_slots(session: Session, centre_id: int, now: datetime | None = None) -> None:
    """After the 60-minute grace period, release an absent booking to standby."""
    now = now or datetime.now()
    lots = session.scalars(
        select(Lot).join(Slot, Lot.slot_id == Slot.id).where(
            Lot.centre_id == centre_id,
            Lot.state == "REGISTERED",
            Lot.standby.is_(False),
            Slot.for_date == now.date(),
            Slot.hour + 1 <= now.hour,
        )
    ).all()
    for lot in lots:
        slot = session.get(Slot, lot.slot_id)
        if slot is None:
            continue
        slot.booked_qtl = max(Decimal("0"), (slot.booked_qtl or Decimal("0")) - (lot.declared_qtl or Decimal("0")))
        lot.standby = True


def cancellation_releases_allowance(session: Session, lot: Lot) -> None:
    if lot.slot_id is None:
        return
    slot = session.get(Slot, lot.slot_id)
    if slot is not None and not lot.standby:
        slot.booked_qtl = max(Decimal("0"), (slot.booked_qtl or Decimal("0")) - (lot.declared_qtl or Decimal("0")))
