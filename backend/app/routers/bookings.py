from datetime import date
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.auth_service import identity_for
from app.booking import allocate_first_fit, cancellation_releases_allowance, release_missed_slots, slots_for_capacity
from app.lifecycle import transition_lot
from app.models import Centre, CentreDailyCapacity, Farmer, Lot, LotEvent, Notification, SessionLocal, Slot
from app.notify import message_for
from app.queue_service import calculate_estimated_wait, get_centre_counters, get_centre_ewma
from app.schemas import BookingInput, BookingView, CentreAvailability, CentreNearby, LotStatus



router = APIRouter(tags=["bookings"])


def _farmer_id(authorization: str | None) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Farmer authentication required.")
    identity = identity_for(authorization.removeprefix("Bearer "))
    if identity is None or identity.role != "FARMER":
        raise HTTPException(status_code=401, detail="Farmer authentication required.")
    return identity.subject_id


def _distance_km(lat1: Decimal, lng1: Decimal, lat2: Decimal | None, lng2: Decimal | None) -> Decimal | None:
    if lat2 is None or lng2 is None:
        return None
    earth = 6371
    delta_lat, delta_lng = radians(float(lat2 - lat1)), radians(float(lng2 - lng1))
    a = sin(delta_lat / 2) ** 2 + cos(radians(float(lat1))) * cos(radians(float(lat2))) * sin(delta_lng / 2) ** 2
    return Decimal(str(round(2 * earth * asin(sqrt(a)), 2)))


def _choke_reason(capacity: CentreDailyCapacity) -> str:
    if capacity.binding_constraint == "YARD" and (capacity.trucks or 0) == 0:
        return f"Trucks unavailable, backlog {capacity.stock_open} quintals"
    return f"{capacity.binding_constraint} is limiting capacity"


def _availability(session, centre: Centre, for_date: date, qtl: Decimal) -> CentreAvailability:
    capacity = session.scalar(select(CentreDailyCapacity).where(CentreDailyCapacity.centre_id == centre.id, CentreDailyCapacity.for_date == for_date))
    if capacity is None:
        return CentreAvailability(centre_id=centre.id, date=for_date, status="Filling", available_qtl=Decimal("0"), reason="Capacity not entered for this date")
    release_missed_slots(session, centre.id)
    slots = slots_for_capacity(session, capacity, centre.open_hour or 9)
    available = sum(((slot.allowance_qtl or Decimal("0")) - (slot.booked_qtl or Decimal("0")) for slot in slots), Decimal("0"))
    if capacity.choked:
        return CentreAvailability(centre_id=centre.id, date=for_date, status="Choked", available_qtl=available, reason=_choke_reason(capacity))
    status = "Open" if allocate_first_fit(slots, qtl) else "Filling"
    return CentreAvailability(centre_id=centre.id, date=for_date, status=status, available_qtl=available)


def _alternatives(session, centre_id: int, for_date: date, qtl: Decimal, lat: Decimal | None = None, lng: Decimal | None = None) -> list[CentreNearby]:
    from datetime import timedelta
    origin = session.get(Centre, centre_id)
    if lat is None and origin is not None:
        lat = origin.latitude
    if lng is None and origin is not None:
        lng = origin.longitude

    centres = session.scalars(select(Centre).where(Centre.active.is_(True), Centre.id != centre_id)).all()
    alternatives = []
    for centre in centres:
        for day_offset in range(14):
            check_date = for_date + timedelta(days=day_offset)
            availability = _availability(session, centre, check_date, qtl)
            if availability.status == "Open":
                distance = _distance_km(lat, lng, centre.latitude, centre.longitude) if lat is not None and lng is not None else None
                alternatives.append(CentreNearby(centre_id=centre.id, name=centre.name, district=centre.district, next_available_date=check_date, distance_km=distance, status="Open"))
                break
    return sorted(alternatives, key=lambda item: item.distance_km if item.distance_km is not None else Decimal("999999"))


@router.get("/centres/nearby", response_model=list[CentreNearby])
def nearby_centres(lat: Decimal, lng: Decimal, date: date, qtl: Decimal, district: str | None = None):
    with SessionLocal.begin() as session:
        statement = select(Centre).where(Centre.active.is_(True))
        if district:
            statement = statement.where(Centre.district == district)
        response = []
        for centre in session.scalars(statement).all():
            availability = _availability(session, centre, date, qtl)
            response.append(CentreNearby(centre_id=centre.id, name=centre.name, district=centre.district, next_available_date=date, distance_km=_distance_km(lat, lng, centre.latitude, centre.longitude), status=availability.status, reason=availability.reason))
        return sorted(response, key=lambda item: item.distance_km if item.distance_km is not None else Decimal("999999"))


@router.get("/centres/{centre_id}/availability", response_model=CentreAvailability)
def centre_availability(centre_id: int, date: date, qtl: Decimal):
    with SessionLocal.begin() as session:
        centre = session.get(Centre, centre_id)
        if centre is None:
            raise HTTPException(status_code=404, detail="Centre not found.")
        return _availability(session, centre, date, qtl)


@router.post("/bookings", response_model=BookingView)
def create_booking(data: BookingInput, authorization: str | None = Header(default=None)):
    farmer_id = _farmer_id(authorization)
    with SessionLocal() as session:
        centre = session.get(Centre, data.centre_id)
        if centre is None or not centre.active:
            raise HTTPException(status_code=404, detail="Centre not found.")
        availability = _availability(session, centre, data.date, data.declared_qtl)
        if availability.status == "Choked":
            alternatives = _alternatives(session, centre.id, data.date, data.declared_qtl)
            farmer = session.get(Farmer, farmer_id)
            nearest = alternatives[0] if alternatives else None
            session.add(Notification(
                phone=farmer.phone if farmer else None,
                body=message_for("CHOKED", None, {"centre": centre.name, "date": str(data.date), "alt": nearest.name if nearest else "none", "alt_date": str(nearest.next_available_date) if nearest else ""}),
                channel="SMS", status="QUEUED",
            ))
            session.commit()
            raise HTTPException(status_code=409, detail={"reason": availability.reason, "alternatives": [item.model_dump(mode="json") for item in alternatives]})
        capacity = session.scalar(select(CentreDailyCapacity).where(CentreDailyCapacity.centre_id == centre.id, CentreDailyCapacity.for_date == data.date))
        if capacity is None:
            raise HTTPException(status_code=409, detail="Capacity is not available for the requested date.")
        slot = allocate_first_fit(slots_for_capacity(session, capacity, centre.open_hour or 9), data.declared_qtl)
        if slot is None:
            raise HTTPException(status_code=409, detail="No hourly allowance can fit the declared quintals.")
        slot.booked_qtl = (slot.booked_qtl or Decimal("0")) + data.declared_qtl
        lot = Lot(farmer_id=farmer_id, centre_id=centre.id, slot_id=slot.id, crop=data.crop, declared_qtl=data.declared_qtl, state="REGISTERED", standby=False)
        session.add(lot)
        session.flush()
        farmer = session.get(Farmer, farmer_id)
        transition_lot(
            session, lot, to_state="REGISTERED", actor_type="SYSTEM", actor_id=None,
            payload={"centre": centre.name, "date": str(data.date), "hour": slot.hour, "declared_qtl": str(data.declared_qtl)},
            phone=farmer.phone if farmer else None, initial=True,
        )
        session.commit()
        return BookingView(lot_id=lot.id, centre_id=centre.id, date=data.date, hour=slot.hour, state=lot.state)


@router.get("/bookings/mine", response_model=list[BookingView])
def my_bookings(authorization: str | None = Header(default=None)):
    farmer_id = _farmer_id(authorization)
    with SessionLocal() as session:
        lots = session.scalars(select(Lot).where(Lot.farmer_id == farmer_id).order_by(Lot.created_at.desc())).all()
        result = []
        for lot in lots:
            slot = session.get(Slot, lot.slot_id) if lot.slot_id else None
            if slot:
                result.append(BookingView(lot_id=lot.id, centre_id=lot.centre_id, date=slot.for_date, hour=slot.hour, state=lot.state or "REGISTERED"))
        return result


@router.delete("/bookings/{lot_id}")
def cancel_booking(lot_id: int, authorization: str | None = Header(default=None)):
    farmer_id = _farmer_id(authorization)
    with SessionLocal.begin() as session:
        lot = session.get(Lot, lot_id)
        if lot is None or lot.farmer_id != farmer_id:
            raise HTTPException(status_code=404, detail="Booking not found.")
        if lot.state != "REGISTERED":
            raise HTTPException(status_code=409, detail="Only a registered booking may be cancelled.")
        cancellation_releases_allowance(session, lot)
        session.delete(lot)
    return {"cancelled": True}


@router.get("/lots/{lot_id}/status", response_model=LotStatus)
def lot_status(lot_id: int, authorization: str | None = Header(default=None)):
    farmer_id = _farmer_id(authorization)
    with SessionLocal() as session:
        lot = session.get(Lot, lot_id)
        if lot is None or lot.farmer_id != farmer_id:
            raise HTTPException(status_code=404, detail="Lot not found.")
        events = session.scalars(select(LotEvent).where(LotEvent.lot_id == lot.id).order_by(LotEvent.created_at)).all()
        queue_position = None
        estimated_wait_minutes = None
        if lot.state == "ARRIVED":
            ahead = session.scalars(select(Lot).where(Lot.centre_id == lot.centre_id, Lot.state == "ARRIVED", Lot.token_no < lot.token_no)).all()
            lots_ahead = len(ahead)
            queue_position = lots_ahead + 1
            ewma = get_centre_ewma(session, lot.centre_id)
            counters = get_centre_counters(session, lot.centre_id)
            estimated_wait_minutes = calculate_estimated_wait(lots_ahead, ewma, counters)
        return LotStatus(lot_id=lot.id, state=lot.state or "REGISTERED", events=[{"from_state": event.from_state, "to_state": event.to_state, "created_at": event.created_at, "payload": event.payload, "correction_of": event.correction_of} for event in events], queue_position=queue_position, estimated_wait_minutes=estimated_wait_minutes)


@router.get("/centres/{centre_id}/queue")
def public_queue(centre_id: int):
    with SessionLocal() as session:
        lots = session.scalars(select(Lot).where(Lot.centre_id == centre_id, Lot.state == "ARRIVED").order_by(Lot.token_no)).all()
        ewma = get_centre_ewma(session, centre_id)
        counters = get_centre_counters(session, centre_id)
        return {"centre_id": centre_id, "queue": [{"token_no": lot.token_no, "lot_id": lot.id, "position": index + 1, "estimated_wait_minutes": calculate_estimated_wait(index, ewma, counters)} for index, lot in enumerate(lots)]}


@router.get("/dev/notifications")
def mock_notification_inbox():
    """Read-only demo SMS inbox backed by the existing notifications table."""
    with SessionLocal() as session:
        rows = session.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(50)).all()
        return [{"id": row.id, "phone": row.phone, "body": row.body, "status": row.status, "created_at": row.created_at, "sent_at": row.sent_at} for row in rows]
