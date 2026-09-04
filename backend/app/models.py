"""SQLAlchemy models for the nine PostgreSQL tables in the build specification."""

import os
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:password@localhost:5432/ps26032",
    )


engine = create_engine(database_url())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Farmer(Base):
    __tablename__ = "farmers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    village: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120))
    land_acres: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Centre(Base):
    __tablename__ = "centres"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    district: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    open_hour: Mapped[int] = mapped_column(Integer, default=9)
    close_hour: Mapped[int] = mapped_column(Integer, default=17)
    buffer_capacity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CentreUser(Base):
    __tablename__ = "centre_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    centre_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("centres.id"))
    username: Mapped[str | None] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(String(20))


class CentreDailyCapacity(Base):
    __tablename__ = "centre_daily_capacity"
    __table_args__ = (UniqueConstraint("centre_id", "for_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    centre_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("centres.id"))
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    counters: Mapped[int | None] = mapped_column(Integer)
    rate_per_counter: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    hours: Mapped[int | None] = mapped_column(Integer)
    bags_available: Mapped[int | None] = mapped_column(Integer)
    qtl_per_bag: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=Decimal("0.4"))
    hamalis: Mapped[int | None] = mapped_column(Integer)
    rate_per_hamali: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    stock_open: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    trucks: Mapped[int | None] = mapped_column(Integer)
    trips_per_truck: Mapped[int | None] = mapped_column(Integer, default=1)
    qtl_per_truck: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), default=Decimal("250"))
    daily_capacity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    binding_constraint: Mapped[str | None] = mapped_column(String(12))
    choked: Mapped[bool | None] = mapped_column(Boolean)


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("centre_id", "for_date", "hour"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    centre_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("centres.id"))
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    allowance_qtl: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    booked_qtl: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=Decimal("0"))


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    farmer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("farmers.id"))
    centre_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("centres.id"))
    slot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("slots.id"))
    crop: Mapped[str | None] = mapped_column(String(40))
    declared_qtl: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    gross_qtl: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    net_qtl: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    grade: Mapped[str | None] = mapped_column(String(10))
    moisture_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    amount_due: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    token_no: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str | None] = mapped_column(String(12), default="REGISTERED")
    standby: Mapped[bool | None] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LotEvent(Base):
    __tablename__ = "lot_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("lots.id"))
    from_state: Mapped[str | None] = mapped_column(String(12))
    to_state: Mapped[str | None] = mapped_column(String(12))
    actor_type: Mapped[str | None] = mapped_column(String(12))
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    correction_of: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("lot_events.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("lots.id"))
    phone: Mapped[str | None] = mapped_column(String(15))
    body: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(10), default="SMS")
    status: Mapped[str | None] = mapped_column(String(10), default="QUEUED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceTime(Base):
    __tablename__ = "service_times"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    centre_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("centres.id"))
    lot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("lots.id"))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weighed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
