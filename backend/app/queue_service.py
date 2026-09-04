"""Queue wait time estimation and service time tracking."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CentreDailyCapacity, Lot, LotEvent, ServiceTime


DEFAULT_EWMA_SEED = 12.0
ALPHA = 0.3


# -----------------------------------------------------------------------------
# Pure Arithmetic Functions
# -----------------------------------------------------------------------------

def calculate_ewma_from_history(
    history: list[float],
    seed: float = DEFAULT_EWMA_SEED,
    alpha: float = ALPHA,
) -> float:
    """Calculate the exponentially weighted moving average for a series of service times.

    Seeds at 12 minutes for a centre with no history, updating as:
    ewma_new = alpha * latest_minutes + (1 - alpha) * ewma_previous
    """
    ewma = float(seed)
    for minutes in history:
        ewma = alpha * float(minutes) + (1.0 - alpha) * ewma
    return ewma


def calculate_estimated_wait(
    lots_ahead: int,
    ewma: float,
    counters_open: int,
) -> float:
    """Calculate queue wait estimation in minutes:

    estimated_wait_minutes = (lots ahead in queue) * ewma / counters_open
    """
    if lots_ahead <= 0:
        return 0.0
    counters = max(1, counters_open)
    return (float(lots_ahead) * float(ewma)) / float(counters)


# -----------------------------------------------------------------------------
# Database Helper Functions
# -----------------------------------------------------------------------------

def get_centre_counters(session: Session, centre_id: int, for_date: date | None = None) -> int:
    """Get open counters from centre_daily_capacity for the date (defaults to today)."""
    if for_date is None:
        for_date = date.today()
    capacity = session.scalar(
        select(CentreDailyCapacity).where(
            CentreDailyCapacity.centre_id == centre_id,
            CentreDailyCapacity.for_date == for_date,
        )
    )
    if capacity is not None and capacity.counters is not None and capacity.counters > 0:
        return capacity.counters
    return 1


def get_centre_ewma(session: Session, centre_id: int) -> float:
    """Fetch history from service_times for a centre and return its current EWMA."""
    rows = session.scalars(
        select(ServiceTime.minutes)
        .where(ServiceTime.centre_id == centre_id)
        .order_by(ServiceTime.id)
    ).all()
    history = [float(m) for m in rows if m is not None]
    return calculate_ewma_from_history(history)


def record_service_time(
    session: Session,
    lot: Lot,
    weighed_at: datetime | None = None,
) -> ServiceTime | None:
    """On a WEIGHED event, record minutes between ARRIVED and WEIGHED in service_times."""
    arrived_event = session.scalar(
        select(LotEvent)
        .where(LotEvent.lot_id == lot.id, LotEvent.to_state == "ARRIVED")
        .order_by(LotEvent.created_at)
    )
    if arrived_event is None or arrived_event.created_at is None:
        return None

    arrived_at = arrived_event.created_at
    weighed_at = weighed_at or datetime.now(timezone.utc)
    duration_seconds = (weighed_at - arrived_at).total_seconds()
    minutes = max(0.0, duration_seconds / 60.0)

    st = ServiceTime(
        centre_id=lot.centre_id,
        lot_id=lot.id,
        arrived_at=arrived_at,
        weighed_at=weighed_at,
        minutes=Decimal(str(round(minutes, 2))),
    )
    session.add(st)
    session.flush()
    return st
