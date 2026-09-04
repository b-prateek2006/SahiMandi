"""District Officer API endpoints for multi-centre overview and drilldown."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from app.models import Centre, CentreDailyCapacity, Lot, SessionLocal
from app.schemas import DistrictCentreDrilldown, DistrictCentreOverview


router = APIRouter(prefix="/district", tags=["district"])


def _calculate_backlog(session, centre_id: int, stock_open: Decimal | None) -> Decimal:
    """Backlog = unlifted yard stock + declared quintals of queued (REGISTERED / ARRIVED) lots."""
    base_stock = stock_open or Decimal("0")
    queued_qtl = session.scalar(
        select(func.coalesce(func.sum(Lot.declared_qtl), Decimal("0")))
        .where(
            Lot.centre_id == centre_id,
            Lot.state.in_(("REGISTERED", "ARRIVED")),
        )
    ) or Decimal("0")
    return base_stock + queued_qtl


@router.get("/overview", response_model=list[DistrictCentreOverview])
def district_overview(district: str | None = None) -> list[DistrictCentreOverview]:
    """Return read-only overview of centres with capacity, binding constraint, backlog, and choked flag."""
    with SessionLocal() as session:
        statement = select(Centre).where(Centre.active.is_(True))
        if district:
            statement = statement.where(Centre.district == district)
        centres = session.scalars(statement).all()

        overview_list = []
        for centre in centres:
            capacity = session.scalar(
                select(CentreDailyCapacity)
                .where(CentreDailyCapacity.centre_id == centre.id)
                .order_by(CentreDailyCapacity.for_date.desc())
            )
            daily_cap = capacity.daily_capacity if capacity else None
            binding = capacity.binding_constraint if capacity else None
            choked = bool(capacity.choked) if capacity else False
            stock_open = capacity.stock_open if capacity else None

            backlog = _calculate_backlog(session, centre.id, stock_open)

            overview_list.append(
                DistrictCentreOverview(
                    centre_id=centre.id,
                    name=centre.name,
                    district=centre.district,
                    daily_capacity=daily_cap,
                    binding_constraint=binding,
                    backlog_qtl=backlog,
                    choked=choked,
                )
            )

        return overview_list


@router.get("/centre/{centre_id}", response_model=DistrictCentreDrilldown)
def district_centre_drilldown(centre_id: int) -> DistrictCentreDrilldown:
    """Return detailed drilldown for one centre."""
    with SessionLocal() as session:
        centre = session.get(Centre, centre_id)
        if centre is None or not centre.active:
            raise HTTPException(status_code=404, detail="Centre not found.")

        capacity = session.scalar(
            select(CentreDailyCapacity)
            .where(CentreDailyCapacity.centre_id == centre.id)
            .order_by(CentreDailyCapacity.for_date.desc())
        )

        backlog = _calculate_backlog(session, centre.id, capacity.stock_open if capacity else None)

        active_lots_count = session.scalar(
            select(func.count(Lot.id)).where(
                Lot.centre_id == centre.id,
                Lot.state.in_(("REGISTERED", "ARRIVED", "WEIGHED", "GRADED", "LIFTED")),
            )
        ) or 0

        return DistrictCentreDrilldown(
            centre_id=centre.id,
            name=centre.name,
            district=centre.district,
            latitude=centre.latitude,
            longitude=centre.longitude,
            buffer_capacity=centre.buffer_capacity,
            daily_capacity=capacity.daily_capacity if capacity else None,
            binding_constraint=capacity.binding_constraint if capacity else None,
            choked=bool(capacity.choked) if capacity else False,
            stock_open=capacity.stock_open if capacity else None,
            backlog_qtl=backlog,
            counters=capacity.counters if capacity else None,
            rate_per_counter=capacity.rate_per_counter if capacity else None,
            hours=capacity.hours if capacity else None,
            bags_available=capacity.bags_available if capacity else None,
            hamalis=capacity.hamalis if capacity else None,
            trucks=capacity.trucks if capacity else None,
            active_lots_count=active_lots_count,
        )
