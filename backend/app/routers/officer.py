"""Centre-officer capacity, queue, and lifecycle endpoints."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.booking import no_show_rate
from app.capacity import CapacityInputs, calculate_bookable_qtl, calculate_capacity
from app.lifecycle import InvalidTransition, transition_lot
from app.models import Centre, CentreDailyCapacity, Farmer, Lot, SessionLocal
from app.queue_service import (
    calculate_estimated_wait,
    get_centre_counters,
    get_centre_ewma,
    record_service_time,
)

from app.schemas import (
    ArriveInput,
    CorrectInput,
    DailyCapacityInput,
    DailyCapacityResult,
    GradeInput,
    LiftInput,
    LotQueueItem,
    SettleInput,
    WeighInput,
)


router = APIRouter(prefix="/officer", tags=["officer"])


def _lot_for_centre(lot_id: int, centre_id: int, session) -> Lot:
    lot = session.get(Lot, lot_id)
    if lot is None or lot.centre_id != centre_id:
        raise HTTPException(status_code=404, detail="Lot not found at this centre.")
    return lot


def _phone_for_lot(lot: Lot, session) -> str | None:
    farmer = session.get(Farmer, lot.farmer_id)
    return farmer.phone if farmer else None


def _transition_or_400(**kwargs):
    try:
        return transition_lot(**kwargs)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/capacity", response_model=DailyCapacityResult)
def save_daily_capacity(data: DailyCapacityInput) -> DailyCapacityResult:
    with SessionLocal.begin() as session:
        centre = session.get(Centre, data.centre_id)
        if centre is None:
            raise HTTPException(status_code=404, detail="Centre not found.")

        centre.buffer_capacity = data.buffer_capacity
        inputs = CapacityInputs(
            counters=data.counters,
            rate_per_counter=data.rate_per_counter,
            hours=data.hours,
            bags_available=data.bags_available,
            qtl_per_bag=data.qtl_per_bag,
            hamalis=data.hamalis,
            rate_per_hamali=data.rate_per_hamali,
            buffer_capacity=data.buffer_capacity,
            stock_open=data.stock_open,
            trucks=data.trucks,
            trips_per_truck=data.trips_per_truck,
            qtl_per_truck=data.qtl_per_truck,
        )
        result = calculate_capacity(inputs)
        existing = session.scalar(
            select(CentreDailyCapacity).where(
                CentreDailyCapacity.centre_id == data.centre_id,
                CentreDailyCapacity.for_date == data.for_date,
            )
        )
        capacity = existing or CentreDailyCapacity(
            centre_id=data.centre_id, for_date=data.for_date
        )
        for field, value in data.model_dump(exclude={"centre_id", "for_date", "buffer_capacity"}).items():
            setattr(capacity, field, value)
        capacity.daily_capacity = result.daily_capacity
        capacity.binding_constraint = result.binding_constraint
        capacity.choked = result.choked
        session.add(capacity)

        rate = no_show_rate(session, data.centre_id, data.for_date)
        bookable_qtl = calculate_bookable_qtl(result.daily_capacity, rate)
        return DailyCapacityResult(
            **result.__dict__, bookable_qtl=bookable_qtl
        )


@router.get("/queue", response_model=list[LotQueueItem])
def today_queue(centre_id: int, for_date: date | None = None) -> list[LotQueueItem]:
    del for_date  # Queue is today's centre queue; slots are introduced with booking.
    with SessionLocal() as session:
        lots = session.scalars(
            select(Lot)
            .where(Lot.centre_id == centre_id)
            .where(Lot.state.in_(("REGISTERED", "ARRIVED", "WEIGHED", "GRADED", "LIFTED")))
            .order_by(Lot.token_no.is_(None), Lot.token_no, Lot.created_at)
        ).all()
        ewma = get_centre_ewma(session, centre_id)
        counters = get_centre_counters(session, centre_id)
        result = []
        for lot in lots:
            wait_minutes = None
            if lot.state == "ARRIVED" and lot.token_no is not None:
                ahead_count = len([
                    l for l in lots
                    if l.state == "ARRIVED" and l.token_no is not None and l.token_no < lot.token_no
                ])
                wait_minutes = calculate_estimated_wait(ahead_count, ewma, counters)
            result.append(
                LotQueueItem(
                    id=lot.id,
                    farmer_id=lot.farmer_id,
                    crop=lot.crop,
                    declared_qtl=lot.declared_qtl,
                    token_no=lot.token_no,
                    state=lot.state,
                    standby=lot.standby,
                    estimated_wait_minutes=wait_minutes,
                )
            )
        return result


@router.post("/lots/{lot_id}/arrive")
def arrive(lot_id: int, data: ArriveInput):
    with SessionLocal.begin() as session:
        lot = _lot_for_centre(lot_id, data.centre_id, session)
        lot.token_no = data.token_no
        ahead = session.scalars(
            select(Lot).where(
                Lot.centre_id == lot.centre_id,
                Lot.state == "ARRIVED",
                Lot.token_no < data.token_no,
            )
        ).all()
        lots_ahead = len(ahead)
        ewma = get_centre_ewma(session, lot.centre_id)
        counters = get_centre_counters(session, lot.centre_id)
        estimated_wait = calculate_estimated_wait(lots_ahead, ewma, counters)
        payload = {
            "token_no": data.token_no,
            "ahead": lots_ahead,
            "wait": int(round(estimated_wait)),
        }
        event = _transition_or_400(
            session=session, lot=lot, to_state="ARRIVED", actor_type="OFFICER",
            actor_id=data.actor_id, payload=payload,
            phone=_phone_for_lot(lot, session),
        )
        return {"event_id": event.id, "state": lot.state, "estimated_wait_minutes": estimated_wait}


@router.post("/lots/{lot_id}/weigh")
def weigh(lot_id: int, data: WeighInput):
    with SessionLocal.begin() as session:
        lot = _lot_for_centre(lot_id, data.centre_id, session)
        lot.gross_qtl = data.gross_qtl
        record_service_time(session, lot)
        event = _transition_or_400(
            session=session, lot=lot, to_state="WEIGHED", actor_type="OFFICER",
            actor_id=data.actor_id, payload={"gross_qtl": str(data.gross_qtl)},
            phone=_phone_for_lot(lot, session),
        )
        return {"event_id": event.id, "state": lot.state}


@router.post("/lots/{lot_id}/grade")
def grade(lot_id: int, data: GradeInput):
    with SessionLocal.begin() as session:
        lot = _lot_for_centre(lot_id, data.centre_id, session)
        lot.grade, lot.moisture_pct = data.grade, data.moisture_pct
        lot.net_qtl, lot.amount_due = data.net_qtl, data.amount_due
        event = _transition_or_400(
            session=session, lot=lot, to_state="GRADED", actor_type="OFFICER",
            actor_id=data.actor_id,
            payload={"grade": data.grade, "moisture_pct": str(data.moisture_pct), "net_qtl": str(data.net_qtl), "amount_due": str(data.amount_due)},
            phone=_phone_for_lot(lot, session),
        )
        return {"event_id": event.id, "state": lot.state}


@router.post("/lots/{lot_id}/lift")
def lift(lot_id: int, data: LiftInput):
    with SessionLocal.begin() as session:
        lot = _lot_for_centre(lot_id, data.centre_id, session)
        event = _transition_or_400(
            session=session, lot=lot, to_state="LIFTED", actor_type="OFFICER",
            actor_id=data.actor_id, payload={"truck_no": data.truck_no, "mill": data.mill},
            phone=_phone_for_lot(lot, session),
        )
        return {"event_id": event.id, "state": lot.state}


@router.post("/lots/{lot_id}/settle")
def settle(lot_id: int, data: SettleInput):
    with SessionLocal.begin() as session:
        lot = _lot_for_centre(lot_id, data.centre_id, session)
        lot.amount_due = data.amount
        event = _transition_or_400(
            session=session, lot=lot, to_state="SETTLED", actor_type="CLERK",
            actor_id=data.actor_id, payload={"reference": data.reference, "amount": str(data.amount)},
            phone=_phone_for_lot(lot, session),
        )
        return {"event_id": event.id, "state": lot.state}


@router.post("/lots/{lot_id}/correct")
def correct(lot_id: int, data: CorrectInput):
    with SessionLocal.begin() as session:
        lot = _lot_for_centre(lot_id, data.centre_id, session)
        event = _transition_or_400(
            session=session, lot=lot, to_state=lot.state or "REGISTERED",
            actor_type="OFFICER", actor_id=data.actor_id, payload=data.payload,
            phone=_phone_for_lot(lot, session), correction_of=data.event_id,
        )
        return {"event_id": event.id, "state": lot.state, "correction_of": event.correction_of}
