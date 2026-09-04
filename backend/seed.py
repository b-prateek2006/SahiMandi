"""Seed the specified four procurement centres and sixty farmers."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.capacity import CapacityInputs, calculate_capacity
from app.models import Base, Centre, CentreDailyCapacity, CentreUser, Farmer, SessionLocal, engine
from app.routers.auth import passwords


CENTRES = (
    ("Sehore Procurement Centre", "Sehore", "23.203300", "77.084400", "2500"),
    ("Ashta Procurement Centre", "Sehore", "23.017800", "76.721500", "2200"),
    ("Ichhawar Procurement Centre", "Sehore", "23.147100", "77.019300", "1800"),
    ("Budhni Procurement Centre", "Sehore", "22.785100", "77.680300", "2000"),
)


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        # Seed centres
        centres = []
        for name, district, latitude, longitude, buffer in CENTRES:
            existing = session.scalar(select(Centre).where(Centre.name == name))
            if not existing:
                centre = Centre(
                    name=name,
                    district=district,
                    latitude=Decimal(latitude),
                    longitude=Decimal(longitude),
                    buffer_capacity=Decimal(buffer),
                )
                session.add(centre)
                session.flush()
                centres.append(centre)
            else:
                centres.append(existing)

        # Seed 60 farmers
        for number in range(1, 61):
            phone = f"900000{number:04d}"
            existing = session.scalar(select(Farmer).where(Farmer.phone == phone))
            if not existing:
                session.add(
                    Farmer(
                        phone=phone,
                        name=f"Farmer {number}",
                        village=f"Village {((number - 1) % 12) + 1}",
                        district="Sehore",
                        land_acres=Decimal("1.00") + Decimal(number % 10) / Decimal("2"),
                    )
                )

        # Seed centre users
        for centre in centres:
            username = f"officer{centre.id}"
            existing = session.scalar(select(CentreUser).where(CentreUser.username == username))
            if not existing:
                session.add(
                    CentreUser(
                        centre_id=centre.id,
                        username=username,
                        password_hash=passwords.hash("officer123"),
                        role="OFFICER",
                    )
                )

        # Seed daily capacity defaults for today
        today = date.today()
        for centre in centres:
            existing = session.scalar(
                select(CentreDailyCapacity).where(
                    CentreDailyCapacity.centre_id == centre.id,
                    CentreDailyCapacity.for_date == today,
                )
            )
            if not existing:
                inputs = CapacityInputs(
                    counters=2,
                    rate_per_counter=Decimal("25"),
                    hours=8,
                    bags_available=3000,
                    qtl_per_bag=Decimal("0.4"),
                    hamalis=6,
                    rate_per_hamali=Decimal("90"),
                    buffer_capacity=centre.buffer_capacity or Decimal("2000"),
                    stock_open=Decimal("1800"),
                    trucks=2,
                    trips_per_truck=1,
                    qtl_per_truck=Decimal("250"),
                )
                result = calculate_capacity(inputs)
                session.add(
                    CentreDailyCapacity(
                        centre_id=centre.id,
                        for_date=today,
                        counters=inputs.counters,
                        rate_per_counter=inputs.rate_per_counter,
                        hours=inputs.hours,
                        bags_available=inputs.bags_available,
                        qtl_per_bag=inputs.qtl_per_bag,
                        hamalis=inputs.hamalis,
                        rate_per_hamali=inputs.rate_per_hamali,
                        stock_open=inputs.stock_open,
                        trucks=inputs.trucks,
                        trips_per_truck=inputs.trips_per_truck,
                        qtl_per_truck=inputs.qtl_per_truck,
                        daily_capacity=result.daily_capacity,
                        binding_constraint=result.binding_constraint,
                        choked=result.choked,
                    )
                )

        session.commit()


if __name__ == "__main__":
    seed()
