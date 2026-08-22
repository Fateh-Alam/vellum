from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from vellum.core.db import Database
from vellum.notes.repository import MindNoteRepository
from vellum.sessions.debrief import DebriefRepository
from vellum.sessions.generated_decks import (
    GeneratedDeckCard,
    GeneratedDeckHistoryRepository,
)
from vellum.sessions.manager import SessionManager
from vellum.sessions.models import (
    Session,
    SessionOrigin,
    SessionStatus,
    SessionTopicContext,
)
from vellum.sessions.repository import SessionRepository


class DebriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "vellum.sqlite3")
        self.database.migrate()
        self.clock_value = 1_000.0
        self.sessions = SessionRepository(self.database)
        self.manager = SessionManager(
            self.sessions,
            clock=lambda: self.clock_value,
            id_factory=lambda: "session-1",
        )
        self.debriefs = DebriefRepository(self.database)
        self.generated = GeneratedDeckHistoryRepository(self.database)

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    @staticmethod
    def topic(
        topic_id: str = "renal-tubular",
        label: str = "Renal Tubular Disorders",
        raw: str | None = "#FirstAid::Renal::Renal_Tubular_Disorders",
    ) -> SessionTopicContext:
        return SessionTopicContext(
            topic_id=topic_id,
            label=label,
            path=("Renal", label),
            raw_topic_tag=raw,
        )

    def answer(
        self,
        card_id: int,
        rating: int,
        duration_ms: int | None,
        topic: SessionTopicContext | None = None,
    ) -> None:
        self.clock_value += 1
        self.manager.answer_card(card_id, rating, duration_ms, topic or self.topic())

    def test_summary_counts_repeated_answers_pace_and_error_clusters(self) -> None:
        self.manager.start(
            origin=SessionOrigin.NORMAL,
            starting_due_count=5,
            estimated_total=5,
            estimated_seconds=50,
        )
        for card_id, rating in ((1, 1), (1, 3), (2, 1), (3, 2), (4, 4), (5, 3)):
            self.answer(card_id, rating, 8_000)
        self.clock_value = 1_060
        terminal = self.manager.complete()
        assert terminal is not None

        result = self.debriefs.finalize(terminal, show_completion_card=False)
        assert result is not None
        self.assertEqual(result.unique_card_count, 5)
        self.assertEqual(result.answer_count, 6)
        self.assertEqual(
            (result.again_count, result.hard_count, result.good_count, result.easy_count),
            (2, 1, 2, 1),
        )
        self.assertEqual(result.active_duration_ms, 48_000)
        self.assertAlmostEqual(result.pace_delta_percent or 0, -20.0)
        self.assertTrue(result.topics[0].error_cluster)
        self.assertEqual(result.suggestion["kind"], "recovery")
        self.assertEqual(result.completion_card_state, "none")

    def test_pace_is_omitted_without_five_valid_durations(self) -> None:
        self.manager.start(estimated_total=4, estimated_seconds=40)
        for card_id in range(1, 5):
            self.answer(card_id, 3, 8_000)
        terminal = self.manager.complete()
        assert terminal is not None
        result = self.debriefs.finalize(terminal, show_completion_card=False)
        assert result is not None
        self.assertIsNone(result.pace_delta_percent)

    def test_generated_completion_waits_for_safe_removal_and_persists_card_state(self) -> None:
        session = self.manager.start(
            deck_id=77,
            deck_name="Vellum Recovery · Renal Tubular Disorders",
            origin=SessionOrigin.RECOVERY,
            estimated_total=3,
            estimated_seconds=30,
        )
        cards = tuple(
            GeneratedDeckCard(card_id, card_id + 10, 1, "Medicine", card_id, "review")
            for card_id in (1, 2, 3)
        )
        self.generated.create(session, feature="recovery", cards=cards)
        self.answer(1, 1, 9_000)
        terminal = self.manager.abandon()
        assert terminal is not None
        self.generated.mark_status(terminal)

        self.assertIsNone(
            self.debriefs.finalize(terminal, show_completion_card=True),
            "A terminal session is not finalized until its owned deck is removed",
        )
        self.generated.mark_removed(terminal.id, reason="explicit_finish", removed_at=1_100)
        result = self.debriefs.finalize(terminal, show_completion_card=True)
        assert result is not None
        self.assertEqual(result.remaining_card_count, 2)
        self.assertEqual(result.suggestion["kind"], "time_machine")
        self.assertEqual(self.debriefs.pending_completion().session_id, terminal.id)
        self.debriefs.set_completion_state(terminal.id, "dismissed")
        self.assertIsNone(self.debriefs.pending_completion())
        self.assertEqual(
            self.debriefs.get(terminal.id).completion_card_state, "dismissed"
        )

    def test_created_and_resurfaced_notes_are_deduplicated_by_event(self) -> None:
        session = self.manager.start()
        note = MindNoteRepository(self.database).create(
            topic_id="renal-tubular",
            topic_label="Renal Tubular Disorders",
            topic_path=("Renal", "Renal Tubular Disorders"),
            body="Revisit the acid-base table.",
            source_card_id=1,
            created_at=1_000,
        )
        self.assertTrue(self.debriefs.record_mind_note_event(session.id, note.id, "created"))
        self.assertFalse(self.debriefs.record_mind_note_event(session.id, note.id, "created"))
        self.assertTrue(self.debriefs.record_mind_note_event(session.id, note.id, "resurfaced"))
        self.answer(1, 3, 4_000)
        terminal = self.manager.complete()
        assert terminal is not None
        result = self.debriefs.finalize(terminal, show_completion_card=False)
        assert result is not None
        self.assertEqual(
            [(item.note_id, item.event_type) for item in result.mind_notes],
            [(note.id, "created"), (note.id, "resurfaced")],
        )

    def test_handoff_replace_clear_acknowledgement_and_pruning_protection(self) -> None:
        first = self._finalized_normal("first", ended_at=100)
        saved = self.debriefs.save_handoff(first.id, "  Continue   renal physiology  ")
        self.assertEqual(saved.handoff_text, "Continue renal physiology")

        second = self._finalized_normal("second", ended_at=200)
        self.debriefs.save_handoff(second.id, "Compare RTA types")
        self.assertIsNotNone(self.debriefs.get(first.id).handoff_acknowledged_at)
        self.assertEqual(self.debriefs.active_handoff().session_id, second.id)

        with self.database.locked() as connection:
            connection.execute(
                "UPDATE session_debriefs SET created_at = 1 WHERE session_id = ?",
                (second.id,),
            )
            connection.commit()
        self.debriefs.prune_normal(history_days=1, maximum_sessions=10)
        self.assertIsNotNone(self.debriefs.get(second.id))
        self.debriefs.save_handoff(second.id, "")
        self.assertIsNone(self.debriefs.active_handoff())

    def test_legacy_topic_rows_get_honest_unavailable_state(self) -> None:
        session = Session(
            id="legacy",
            started_at=100,
            last_active_at=200,
            ended_at=200,
            status=SessionStatus.COMPLETED,
        )
        self.sessions.save(session)
        with self.database.locked() as connection:
            connection.execute(
                """
                INSERT INTO session_cards(
                    session_id, card_id, reviewed_at, rating, duration_ms, topic_id
                ) VALUES ('legacy', 1, 150000, 1, 3000, 'old-topic')
                """
            )
            connection.commit()
        self.assertIsNone(self.debriefs.finalize(session, show_completion_card=False))

    def _finalized_normal(self, session_id: str, *, ended_at: int) -> Session:
        session = Session(
            id=session_id,
            started_at=ended_at - 10,
            last_active_at=ended_at,
            ended_at=ended_at,
            status=SessionStatus.COMPLETED,
            reviewed_count=1,
            estimated_total=1,
        )
        self.sessions.save(session)
        self.sessions.record_answer(
            session,
            card_id=ended_at,
            reviewed_at=ended_at * 1000,
            rating=3,
            duration_ms=2_000,
            topic=self.topic(
                topic_id=f"topic-{session_id}",
                label=f"Topic {session_id}",
                raw=f"Medicine::Topic_{session_id}",
            ),
        )
        result = self.debriefs.finalize(session, show_completion_card=False)
        assert result is not None
        return session


if __name__ == "__main__":
    unittest.main()
