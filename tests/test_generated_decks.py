from pathlib import Path
import tempfile
import unittest

from vellum.core.db import Database
from vellum.sessions.generated_decks import (
    GeneratedDeckCard,
    GeneratedDeckHistoryRepository,
)
from vellum.sessions.manager import SessionManager
from vellum.sessions.models import SessionOrigin, SessionStatus
from vellum.sessions.repository import SessionRepository
from vellum.ui.history import history_details_html


class GeneratedDeckHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "vellum.sqlite3")
        self.database.migrate()
        self.sessions = SessionManager(
            SessionRepository(self.database), id_factory=lambda: "generated-1"
        )
        self.history = GeneratedDeckHistoryRepository(self.database)
        self.session = self.sessions.start(
            deck_id=77,
            deck_name="Vellum Time Machine - 10 min",
            query="all-decks",
            target_seconds=600,
            origin=SessionOrigin.TIME_MACHINE,
            starting_due_count=2,
            estimated_total=2,
        )
        self.cards = (
            GeneratedDeckCard(101, 11, 1, "Cardiology", 1, "review"),
            GeneratedDeckCard(102, 12, 2, "Renal", 2, "learning"),
        )

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_manifest_keeps_every_card_and_every_answer_event(self) -> None:
        self.history.create(
            self.session,
            feature="time_machine",
            cards=self.cards,
            scope="all-decks",
            metadata={"duration_minutes": 10},
        )
        self.assertTrue(
            self.history.record_answer(
                self.session.id,
                card_id=101,
                answered_at=1001,
                rating=1,
                duration_ms=1200,
            )
        )
        self.assertTrue(
            self.history.record_answer(
                self.session.id,
                card_id=101,
                answered_at=1002,
                rating=3,
                duration_ms=900,
            )
        )
        saved = self.history.get(self.session.id)
        self.assertEqual(saved.planned_card_count, 2)
        self.assertEqual(saved.answered_card_count, 1)
        self.assertEqual(len(saved.cards), 2)
        self.assertEqual(len(saved.answers), 2)
        self.assertEqual(saved.cards[0].rating, 3)

    def test_non_manifest_card_answer_is_rejected(self) -> None:
        self.history.create(
            self.session, feature="time_machine", cards=self.cards
        )

    def test_deferred_answer_cannot_reopen_terminal_history(self) -> None:
        self.history.create(
            self.session, feature="time_machine", cards=self.cards
        )
        completed = self.sessions.complete_saved(self.session.id)
        self.history.mark_status(completed)
        self.history.record_answer(
            self.session.id,
            card_id=101,
            answered_at=1001,
            rating=3,
            duration_ms=900,
        )
        saved = self.history.get(self.session.id)
        self.assertEqual(saved.status, SessionStatus.COMPLETED.value)
        self.assertFalse(
            self.history.record_answer(
                self.session.id,
                card_id=999,
                answered_at=1001,
                rating=2,
                duration_ms=None,
            )
        )

    def test_history_survives_session_deletion_and_records_deck_removal(self) -> None:
        self.history.create(
            self.session, feature="time_machine", cards=self.cards
        )
        completed = self.sessions.complete_saved(self.session.id)
        self.history.mark_status(completed)
        self.history.mark_removed(self.session.id, reason="exhausted", removed_at=2000)
        with self.database.locked() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (self.session.id,))
            connection.commit()
        saved = self.history.get(self.session.id)
        self.assertEqual(saved.status, SessionStatus.COMPLETED.value)
        self.assertEqual(saved.removal_reason, "exhausted")
        self.assertEqual(saved.removed_at, 2000)

    def test_startup_repairs_terminal_generated_deck_cleanup(self) -> None:
        self.history.create(
            self.session, feature="time_machine", cards=self.cards
        )
        completed = self.sessions.complete_saved(self.session.id)
        self.history.mark_status(completed)

        class Decks:
            removed: list[int] = []

            @staticmethod
            def is_filtered(deck_id: int) -> bool:
                return deck_id == 77

            @staticmethod
            def name_if_exists(deck_id: int):
                return (
                    "Vellum Time Machine - 10 min" if deck_id == 77 else None
                )

            def remove(self, deck_ids: list[int]) -> None:
                self.removed.extend(deck_ids)

        class Collection:
            decks = Decks()

        self.assertEqual(
            self.history.backfill_sessions(Collection(), (completed,)), 0
        )
        saved = self.history.get(self.session.id)
        self.assertEqual(Collection.decks.removed, [77])
        self.assertIsNotNone(saved.removed_at)
        self.assertEqual(saved.removal_reason, "startup_terminal_cleanup")

    def test_history_view_contains_manifest_not_card_content(self) -> None:
        saved = self.history.create(
            self.session,
            feature="time_machine",
            cards=self.cards,
            metadata={"duration_minutes": 10},
        )
        rendered = history_details_html(saved)
        self.assertIn("Complete card manifest", rendered)
        self.assertIn("Cardiology", rendered)
        self.assertIn("101", rendered)
        self.assertNotIn("Front field", rendered)


if __name__ == "__main__":
    unittest.main()
