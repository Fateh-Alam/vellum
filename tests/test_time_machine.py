import unittest

from vellum.features.time_machine import (
    queue_fetch_limit,
    queued_buckets,
    time_target_reached,
)
from vellum.anki.time_machine import (
    collect_all_deck_queue,
    collect_selected_deck_queue,
    list_time_machine_decks,
)
from vellum.sessions.models import Session, SessionOrigin, SessionStatus
from vellum.timing.models import TimingBucket


class Card:
    def __init__(self, ctype: int) -> None:
        self.ctype = ctype


class QueuedCard:
    def __init__(self, queue: int, ctype: int = 2) -> None:
        self.queue = queue
        self.card = Card(ctype)


class Queue:
    cards = [
        QueuedCard(1, 3),
        QueuedCard(0, 0),
        QueuedCard(1, 1),
        QueuedCard(2, 2),
    ]


class DeckNameId:
    def __init__(self, deck_id: int, name: str) -> None:
        self.id = deck_id
        self.name = name


class QueueCard:
    def __init__(self, card_id: int, queue: int, ctype: int = 2) -> None:
        self.card = Card(ctype)
        self.card.id = card_id
        self.queue = queue


class DeckQueue:
    def __init__(self, cards: list[QueueCard]) -> None:
        self.cards = cards
        self.new_count = sum(card.queue == 0 for card in cards)
        self.learning_count = sum(card.queue == 1 for card in cards)
        self.review_count = sum(card.queue == 2 for card in cards)


class FakeDecks:
    def __init__(self) -> None:
        self.current_id = 22
        self.history: list[int] = []

    def get_current_id(self) -> int:
        return self.current_id

    def set_current(self, deck_id: int) -> None:
        self.current_id = deck_id
        self.history.append(deck_id)

    def all_names_and_ids(
        self, *, skip_empty_default: bool, include_filtered: bool
    ) -> list[DeckNameId]:
        self.arguments = (skip_empty_default, include_filtered)
        return [
            DeckNameId(11, "Alpha"),
            DeckNameId(12, "Alpha::Child"),
            DeckNameId(22, "Beta"),
        ]


class FakeScheduler:
    def __init__(self, decks: FakeDecks) -> None:
        self.decks = decks
        self.queues = {
            11: DeckQueue([QueueCard(1, 2), QueueCard(2, 1, 3)]),
            22: DeckQueue([QueueCard(3, 0, 0)]),
        }

    def get_queued_cards(self, fetch_limit: int) -> DeckQueue:
        queue = self.queues.get(self.decks.current_id, DeckQueue([]))
        fetched = DeckQueue(queue.cards[:fetch_limit])
        fetched.new_count = queue.new_count
        fetched.learning_count = queue.learning_count
        fetched.review_count = queue.review_count
        return fetched


class FakeCollection:
    def __init__(self) -> None:
        self.decks = FakeDecks()
        self.sched = FakeScheduler(self.decks)


class TimeMachineTests(unittest.TestCase):
    def test_queue_fetch_limit_scales_with_fast_sessions_and_is_bounded(self) -> None:
        self.assertEqual(queue_fetch_limit(10, 20), 5_000)
        self.assertEqual(queue_fetch_limit(480, 1), 28_800)
        self.assertEqual(queue_fetch_limit(480, 0.25), 100_000)

    def test_scheduler_snapshot_order_and_relearning_are_preserved(self) -> None:
        self.assertEqual(
            queued_buckets(Queue()),
            [
                TimingBucket.RELEARNING,
                TimingBucket.NEW,
                TimingBucket.LEARNING,
                TimingBucket.REVIEW,
            ],
        )

    def test_all_decks_snapshot_uses_top_level_decks_once_and_restores_selection(self) -> None:
        collection = FakeCollection()
        snapshot = collect_all_deck_queue(collection, fetch_limit=100)

        self.assertEqual(snapshot.card_ids, (1, 2, 3))
        self.assertEqual(
            snapshot.buckets,
            (
                TimingBucket.REVIEW,
                TimingBucket.RELEARNING,
                TimingBucket.NEW,
            ),
        )
        self.assertEqual(snapshot.available_cards, 3)
        self.assertEqual(snapshot.active_decks, 2)
        self.assertFalse(snapshot.truncated)
        self.assertEqual(collection.decks.current_id, 22)
        self.assertEqual(collection.decks.history, [11, 22, 22])
        self.assertEqual(collection.decks.arguments, (False, False))

    def test_all_decks_snapshot_marks_safety_cap_truncation(self) -> None:
        collection = FakeCollection()
        snapshot = collect_all_deck_queue(collection, fetch_limit=1)

        self.assertEqual(snapshot.card_ids, (1,))
        self.assertEqual(snapshot.available_cards, 3)
        self.assertTrue(snapshot.truncated)

    def test_deck_choices_include_counts_and_restore_selection(self) -> None:
        collection = FakeCollection()

        choices = list_time_machine_decks(collection)

        self.assertEqual(
            [(choice.deck_name, choice.available_cards) for choice in choices],
            [("Alpha", 2), ("Beta", 1)],
        )
        self.assertEqual(choices[0].learning_cards, 1)
        self.assertEqual(choices[0].review_cards, 1)
        self.assertEqual(collection.decks.current_id, 22)

    def test_selected_decks_exclude_unchecked_groups(self) -> None:
        collection = FakeCollection()

        snapshot = collect_selected_deck_queue(
            collection,
            (11,),
            fetch_limit=100,
        )

        self.assertEqual(snapshot.card_ids, (1, 2))
        self.assertEqual(snapshot.available_cards, 2)
        self.assertEqual(snapshot.active_decks, 1)
        self.assertEqual(collection.decks.current_id, 22)

    def test_selected_decks_ignore_children_and_unknown_ids(self) -> None:
        collection = FakeCollection()

        snapshot = collect_selected_deck_queue(
            collection,
            (12, 999),
            fetch_limit=100,
        )

        self.assertEqual(snapshot.card_ids, ())
        self.assertEqual(snapshot.available_cards, 0)
        self.assertEqual(collection.decks.current_id, 22)

    def test_time_target_is_specific_to_live_time_machine_sessions(self) -> None:
        session = Session(
            id="target",
            started_at=100,
            last_active_at=100,
            status=SessionStatus.ACTIVE,
            origin=SessionOrigin.TIME_MACHINE,
            target_seconds=60,
        )
        self.assertFalse(time_target_reached(session, now=159))
        self.assertTrue(time_target_reached(session, now=160))
        self.assertFalse(
            time_target_reached(
                Session(
                    id="normal",
                    started_at=100,
                    last_active_at=100,
                    status=SessionStatus.ACTIVE,
                    target_seconds=60,
                ),
                now=200,
            )
        )


if __name__ == "__main__":
    unittest.main()
