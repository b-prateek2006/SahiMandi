import inspect
import unittest

from app.lifecycle import InvalidTransition, transition_lot
from app.models import Lot, LotEvent, Notification


class FakeSession:
    def __init__(self, events=()):
        self.events = {event.id: event for event in events}
        self.added = []

    def in_transaction(self):
        return True

    def get(self, model, identity):
        if model is LotEvent:
            return self.events.get(identity)
        return None

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None


class LifecycleTests(unittest.TestCase):
    def test_forward_transition_updates_lot_and_appends_one_event_and_notification(self):
        session = FakeSession()
        lot = Lot(id=1, state="REGISTERED")

        event = transition_lot(
            session, lot, to_state="ARRIVED", actor_type="OFFICER", actor_id=7,
            payload={"token_no": 4}, phone="9000000001",
        )

        self.assertEqual(lot.state, "ARRIVED")
        self.assertIsInstance(event, LotEvent)
        self.assertEqual(event.from_state, "REGISTERED")
        self.assertEqual(event.to_state, "ARRIVED")
        self.assertEqual(event.correction_of, None)
        self.assertEqual(len([row for row in session.added if isinstance(row, LotEvent)]), 1)
        notifications = [row for row in session.added if isinstance(row, Notification)]
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].status, "QUEUED")

    def test_registration_event_is_created_by_the_same_helper(self):
        session = FakeSession()
        lot = Lot(id=1, state="REGISTERED")

        event = transition_lot(
            session, lot, to_state="REGISTERED", actor_type="SYSTEM", actor_id=None,
            payload={"hour": 9}, phone="9000000001", initial=True,
        )

        self.assertIsNone(event.from_state)
        self.assertEqual(event.to_state, "REGISTERED")
        self.assertEqual(len([row for row in session.added if isinstance(row, Notification)]), 1)

    def test_skipped_and_reverse_transitions_are_rejected_without_side_effects(self):
        session = FakeSession()
        lot = Lot(id=1, state="REGISTERED")

        with self.assertRaises(InvalidTransition):
            transition_lot(
                session, lot, to_state="WEIGHED", actor_type="OFFICER", actor_id=7,
                payload={}, phone="9000000001",
            )

        self.assertEqual(lot.state, "REGISTERED")
        self.assertEqual(session.added, [])

    def test_settled_lot_cannot_transition_again(self):
        session = FakeSession()
        lot = Lot(id=1, state="SETTLED")

        with self.assertRaises(InvalidTransition):
            transition_lot(
                session, lot, to_state="ARRIVED", actor_type="OFFICER", actor_id=7,
                payload={}, phone="9000000001",
            )

        self.assertEqual(session.added, [])

    def test_correction_appends_new_event_without_editing_history(self):
        original = LotEvent(id=10, lot_id=1, from_state="ARRIVED", to_state="WEIGHED", payload={"gross_qtl": "20"})
        session = FakeSession(events=(original,))
        lot = Lot(id=1, state="WEIGHED")

        correction = transition_lot(
            session, lot, to_state="WEIGHED", actor_type="OFFICER", actor_id=7,
            payload={"gross_qtl": "19.5"}, phone="9000000001", correction_of=10,
        )

        self.assertEqual(lot.state, "WEIGHED")
        self.assertEqual(correction.correction_of, 10)
        self.assertEqual(original.payload, {"gross_qtl": "20"})
        self.assertEqual(len([row for row in session.added if isinstance(row, LotEvent)]), 1)
        self.assertEqual(len([row for row in session.added if isinstance(row, Notification)]), 1)

    def test_correction_must_reference_an_event_for_the_same_lot(self):
        foreign_event = LotEvent(id=10, lot_id=2)
        session = FakeSession(events=(foreign_event,))
        lot = Lot(id=1, state="WEIGHED")

        with self.assertRaises(InvalidTransition):
            transition_lot(
                session, lot, to_state="WEIGHED", actor_type="OFFICER", actor_id=7,
                payload={}, phone="9000000001", correction_of=10,
            )

        self.assertEqual(session.added, [])

    def test_helper_is_the_only_router_state_side_effect_path(self):
        from app.routers import officer

        router_source = inspect.getsource(officer)
        self.assertNotIn("LotEvent(", router_source)
        self.assertNotIn("Notification(", router_source)


if __name__ == "__main__":
    unittest.main()
