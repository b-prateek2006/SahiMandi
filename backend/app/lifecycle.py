"""The single write path for SahiMandi lot lifecycle side effects."""

from contextlib import nullcontext
from typing import Any

from sqlalchemy.orm import Session

from app.models import Lot, LotEvent, Notification
from app.notify import message_for


LIFECYCLE_STATES = (
    "REGISTERED",
    "ARRIVED",
    "WEIGHED",
    "GRADED",
    "LIFTED",
    "SETTLED",
)
NEXT_STATE = dict(zip(LIFECYCLE_STATES, LIFECYCLE_STATES[1:]))


class InvalidTransition(ValueError):
    """Raised when a lot attempts to skip, reverse, or repeat a state."""


def transition_lot(
    session: Session,
    lot: Lot,
    *,
    to_state: str,
    actor_type: str,
    actor_id: int | None,
    payload: dict[str, Any],
    phone: str | None,
    correction_of: int | None = None,
    initial: bool = False,
) -> LotEvent:
    """Atomically record one lifecycle transition or one correction event.

    This is the only function that changes a lot state and creates the
    corresponding event and queued notification. A correction preserves the
    current state and references the event it corrects.
    """
    transaction = nullcontext() if session.in_transaction() else session.begin()
    with transaction:
        current_state = lot.state or "REGISTERED"

        if initial:
            if current_state != "REGISTERED" or to_state != "REGISTERED":
                raise InvalidTransition("Only a new lot can be registered.")
            from_state = None
        elif correction_of is None:
            expected_state = NEXT_STATE.get(current_state)
            if to_state != expected_state:
                raise InvalidTransition(
                    f"Cannot transition from {current_state} to {to_state}."
                )
            from_state = current_state
        else:
            corrected_event = session.get(LotEvent, correction_of)
            if corrected_event is None or corrected_event.lot_id != lot.id:
                raise InvalidTransition("The correction event must belong to this lot.")
            if to_state != current_state:
                raise InvalidTransition("A correction cannot change the lot lifecycle state.")
            from_state = current_state

        lot.state = to_state
        event = LotEvent(
            lot_id=lot.id,
            from_state=from_state,
            to_state=to_state,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload,
            correction_of=correction_of,
        )
        notification_kind = "BOOKED" if initial else to_state
        notification = Notification(
            lot_id=lot.id,
            phone=phone,
            body=message_for(notification_kind, lot.id, payload),
            channel="SMS",
            status="QUEUED",
        )
        session.add(event)
        session.add(notification)
        session.flush()
        return event
