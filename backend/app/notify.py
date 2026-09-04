"""Queued SMS delivery, templates, and gateway adapters."""

import os
from datetime import datetime, timezone
from typing import Protocol
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Notification


class Gateway(Protocol):
    def send(self, phone: str | None, body: str | None) -> None: ...


def _short(message: str) -> str:
    return message[:159]


def message_for(kind: str, lot_id: int | None, payload: dict) -> str:
    """Build the specified short English + Hindi mock-SMS templates."""
    lot = lot_id if lot_id is not None else "—"
    templates = {
        "BOOKED": f"Slot confirmed. {payload.get('centre', 'Centre')}, {payload.get('date', '')} {payload.get('hour', '')}:00. Lot {lot}. Bring {payload.get('qtl', payload.get('declared_qtl', ''))} qtl. स्लॉट पक्का।",
        "ARRIVED": f"Token {payload.get('token', payload.get('token_no', ''))}. {payload.get('ahead', '—')} ahead. Wait {payload.get('wait', '—')} min. Lot {lot}. टोकन जारी।",
        "WEIGHED": f"Weight recorded {payload.get('gross', payload.get('gross_qtl', ''))} qtl. Lot {lot}. वजन दर्ज।",
        "GRADED": f"Grade {payload.get('grade', '')}, moisture {payload.get('moisture', payload.get('moisture_pct', ''))}%. Net {payload.get('net', payload.get('net_qtl', ''))} qtl. Amount {payload.get('amount', payload.get('amount_due', ''))}. Lot {lot}. ग्रेड दर्ज।",
        "LIFTED": f"Your lot left for {payload.get('mill', '')}. Lot {lot}. लॉट भेजा गया।",
        "SETTLED": f"Payment released. Amount {payload.get('amount', '')}. Ref {payload.get('reference', '')}. Lot {lot}. भुगतान जारी।",
        "CHOKED": f"{payload.get('centre', 'Centre')} cannot accept grain on {payload.get('date', '')}. Nearest open: {payload.get('alt', '')} on {payload.get('alt_date', '')}. केंद्र भरा है।",
    }
    return _short(templates.get(kind, f"Lot {lot} updated. विवरण अपडेट।"))


class MockGateway:
    """Demo gateway: successful delivery makes the database inbox visible to UI."""

    def send(self, phone: str | None, body: str | None) -> None:
        return None


class Msg91Gateway:
    """Real-gateway HTTP shape; never selected unless explicitly configured."""

    def __init__(self, endpoint: str, auth_key: str):
        self.endpoint = endpoint
        self.auth_key = auth_key

    def send(self, phone: str | None, body: str | None) -> None:
        request = Request(
            self.endpoint,
            data=(f"mobile={phone or ''}&message={body or ''}").encode(),
            headers={"authkey": self.auth_key, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            if response.status >= 300:
                raise RuntimeError(f"Msg91 delivery failed with status {response.status}")


def configured_gateway() -> Gateway:
    if os.getenv("SMS_GATEWAY") == "MSG91":
        return Msg91Gateway(os.environ["MSG91_ENDPOINT"], os.environ["MSG91_AUTH_KEY"])
    return MockGateway()


def process_queued_notifications(session_factory: sessionmaker, gateway: Gateway) -> int:
    """Deliver the current queued rows and persist SENT or FAILED outcomes."""
    processed = 0
    with session_factory() as session:
        rows = session.scalars(select(Notification).where(Notification.status == "QUEUED").order_by(Notification.created_at)).all()
        for notification in rows:
            try:
                gateway.send(notification.phone, notification.body)
                notification.status = "SENT"
                notification.sent_at = datetime.now(timezone.utc)
            except Exception:
                notification.status = "FAILED"
            processed += 1
        session.commit()
    return processed
