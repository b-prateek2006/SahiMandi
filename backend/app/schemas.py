"""Pydantic request and response schemas for the officer workflows."""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class DailyCapacityInput(BaseModel):
    centre_id: int
    for_date: date
    counters: int
    rate_per_counter: Decimal
    hours: int
    bags_available: int
    qtl_per_bag: Decimal = Decimal("0.4")
    hamalis: int
    rate_per_hamali: Decimal
    buffer_capacity: Decimal
    stock_open: Decimal
    trucks: int
    trips_per_truck: int = 1
    qtl_per_truck: Decimal = Decimal("250")


class DailyCapacityResult(BaseModel):
    staff_cap: Decimal
    bag_cap: Decimal
    hamali_cap: Decimal
    lift_today: Decimal
    yard_cap: Decimal
    daily_capacity: Decimal
    binding_constraint: str
    choked: bool
    bookable_qtl: Decimal


class ArriveInput(BaseModel):
    centre_id: int
    actor_id: int | None = None
    token_no: int


class WeighInput(BaseModel):
    centre_id: int
    actor_id: int | None = None
    gross_qtl: Decimal


class GradeInput(BaseModel):
    centre_id: int
    actor_id: int | None = None
    grade: str
    moisture_pct: Decimal
    net_qtl: Decimal
    amount_due: Decimal


class LiftInput(BaseModel):
    centre_id: int
    actor_id: int | None = None
    truck_no: str
    mill: str


class SettleInput(BaseModel):
    centre_id: int
    actor_id: int | None = None
    reference: str
    amount: Decimal


class CorrectInput(BaseModel):
    centre_id: int
    actor_id: int | None = None
    event_id: int
    payload: dict[str, Any]


class LotQueueItem(BaseModel):
    id: int
    farmer_id: int | None
    crop: str | None
    declared_qtl: Decimal | None
    token_no: int | None
    state: str | None
    standby: bool | None
    estimated_wait_minutes: float | None = None



class OtpRequest(BaseModel):
    phone: str = Field(max_length=15)


class OtpVerify(OtpRequest):
    code: str = Field(min_length=6, max_length=6)


class OfficerLoginInput(BaseModel):
    username: str
    password: str


class FarmerRegistration(BaseModel):
    phone: str = Field(max_length=15)
    name: str = Field(max_length=120)
    village: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    land_acres: Decimal | None = None


class FarmerView(FarmerRegistration):
    id: int


class BookingInput(BaseModel):
    centre_id: int
    date: date
    crop: str = Field(max_length=40)
    declared_qtl: Decimal


class BookingView(BaseModel):
    lot_id: int
    centre_id: int | None
    date: date
    hour: int
    state: str


class CentreAvailability(BaseModel):
    centre_id: int
    date: date
    status: str
    available_qtl: Decimal
    reason: str | None = None


class CentreNearby(BaseModel):
    centre_id: int
    name: str
    district: str
    next_available_date: date
    distance_km: Decimal | None
    status: str
    reason: str | None = None


class LotStatus(BaseModel):
    lot_id: int
    state: str
    events: list[dict[str, Any]]
    queue_position: int | None = None
    estimated_wait_minutes: float | None = None


class DistrictCentreOverview(BaseModel):
    centre_id: int
    name: str
    district: str
    daily_capacity: Decimal | None = None
    binding_constraint: str | None = None
    backlog_qtl: Decimal = Decimal("0")
    choked: bool = False


class DistrictCentreDrilldown(BaseModel):
    centre_id: int
    name: str
    district: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    buffer_capacity: Decimal | None = None
    daily_capacity: Decimal | None = None
    binding_constraint: str | None = None
    choked: bool = False
    stock_open: Decimal | None = None
    backlog_qtl: Decimal = Decimal("0")
    counters: int | None = None
    rate_per_counter: Decimal | None = None
    hours: int | None = None
    bags_available: int | None = None
    hamalis: int | None = None
    trucks: int | None = None
    active_lots_count: int = 0

