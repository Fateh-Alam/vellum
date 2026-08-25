from pathlib import Path
import tempfile
import unittest

from vellum.core.db import Database
from vellum.core.events import EventBus
from vellum.sessions.manager import SessionManager
from vellum.sessions.models import SessionOrigin, SessionStatus
from vellum.sessions.repository import SessionRepository


class Clock:
    value = 1000

    def __call__(self) -> float:
        return self.value


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "vellum.sqlite3")
        self.db.migrate()
        self.clock = Clock()
        self.repo = SessionRepository(self.db)
        self.manager = SessionManager(
            self.repo, clock=self.clock, id_factory=lambda: "session-1"
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_session_progress_is_checkpointed_and_resumable(self) -> None:
        session = self.manager.start(deck_id=7, deck_name="Renal", starting_due_count=20)
        self.manager.show_card(11, "a" * 40)
        self.clock.value += 8
        answered = self.manager.answer_card(11, 2, 8000, "a" * 40)
        self.assertEqual(answered.reviewed_count, 1)
        interrupted = self.manager.interrupt()
        self.assertEqual(interrupted.status, SessionStatus.INTERRUPTED)
        resumed = self.manager.resume(session.id)
        self.assertEqual(resumed.status, SessionStatus.RESUMED)
        self.assertEqual(resumed.reviewed_count, 1)

    def test_implausible_duration_is_excluded_not_clamped(self) -> None:
        self.manager.start()
        self.manager.answer_card(1, 1, 600_000, None)
        row = self.db.connect().execute(
            "SELECT duration_ms FROM session_cards"
        ).fetchone()
        self.assertIsNone(row[0])

    def test_repeated_same_card_answers_have_distinct_checkpoints(self) -> None:
        self.manager.start()
        self.manager.answer_card(1, 1, 1000, None)
        self.manager.answer_card(1, 2, 1000, None)
        count = self.db.connect().execute(
            "SELECT COUNT(*) FROM session_cards WHERE card_id = 1"
        ).fetchone()[0]
        self.assertEqual(count, 2)
        self.assertEqual(self.manager.current.reviewed_count, 2)

    def test_post_card_target_event_only_fires_after_an_answer(self) -> None:
        events = EventBus()
        answered = []
        events.subscribe("session_card_answered", answered.append)
        self.manager.events = events
        self.manager.start()
        self.manager.show_card(1, None)
        self.assertEqual(answered, [])
        self.manager.answer_card(1, 3, 1000, None)
        self.assertEqual(len(answered), 1)

    def test_inactivity_interrupts_instead_of_silently_continuing(self) -> None:
        self.manager.start()
        self.clock.value += 1801
        with self.assertRaises(RuntimeError):
            self.manager.show_card(2, None)
        self.assertEqual(self.manager.current.status, SessionStatus.INTERRUPTED)

    def test_terminal_session_cannot_resume(self) -> None:
        session = self.manager.start()
        self.manager.complete()
        with self.assertRaises(ValueError):
            self.manager.resume(session.id)

    def test_crash_recovery_preserves_real_last_activity_time(self) -> None:
        session = self.manager.start()
        original_activity = session.last_active_at
        self.repo.interrupt_open_sessions()
        restored = self.repo.get(session.id)
        self.assertEqual(restored.status, SessionStatus.INTERRUPTED)
        self.assertEqual(restored.last_active_at, original_activity)

    def test_corrupt_resume_record_is_removed_instead_of_crashing(self) -> None:
        self.db.connect().execute(
            """
            INSERT INTO sessions(
                id, started_at, last_active_at, status, origin, metadata_json
            ) VALUES ('corrupt', 1, 1, 'interrupted', 'unknown-origin', '{}')
            """
        )
        self.db.connect().commit()
        self.assertIsNone(self.repo.latest_resumable())
        remaining = self.db.connect().execute(
            "SELECT COUNT(*) FROM sessions WHERE id = 'corrupt'"
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_saved_session_can_be_abandoned_without_resuming_it(self) -> None:
        session = self.manager.start()
        self.manager.interrupt()
        abandoned = self.manager.abandon_saved(session.id)
        self.assertEqual(abandoned.status, SessionStatus.ABANDONED)

    def test_resume_preserves_recovery_origin(self) -> None:
        session = self.manager.start(origin=SessionOrigin.RECOVERY)
        self.manager.interrupt()
        resumed = self.manager.resume(session.id)
        self.assertEqual(resumed.origin, SessionOrigin.RECOVERY)

    def test_periodic_checkpoint_does_not_manufacture_activity(self) -> None:
        session = self.manager.start()
        self.clock.value += 30
        checkpoint = self.manager.checkpoint()
        self.assertEqual(checkpoint.last_active_at, session.last_active_at)
        restored = self.repo.get(session.id)
        self.assertEqual(restored.last_active_at, session.last_active_at)

    def test_generated_resume_is_found_even_after_newer_normal_session(self) -> None:
        generated = self.manager.start(
            deck_id=7,
            deck_name="Vellum Time Machine",
            origin=SessionOrigin.TIME_MACHINE,
        )
        self.manager.interrupt()
        self.clock.value += 1
        self.manager.id_factory = lambda: "normal-2"
        normal = self.manager.start(deck_id=9, deck_name="Normal")
        self.manager.interrupt()
        self.assertEqual(self.repo.latest_resumable().id, normal.id)
        self.assertEqual(self.repo.latest_generated_resumable().id, generated.id)
        self.assertEqual(
            self.repo.generated_resumable_for_deck(7, "Vellum Time Machine").id,
            generated.id,
        )
        self.assertEqual(
            tuple(session.id for session in self.repo.generated_sessions()),
            (generated.id,),
        )

    def test_study_builder_is_a_generated_resumable_origin(self) -> None:
        session = self.manager.start(
            deck_id=17,
            deck_name="Vellum Study Builder",
            origin=SessionOrigin.STUDY_BUILDER,
        )
        self.manager.interrupt()
        self.assertEqual(self.repo.latest_generated_resumable().id, session.id)
        self.assertEqual(
            self.repo.generated_resumable_for_deck(17, "Vellum Study Builder").id,
            session.id,
        )


if __name__ == "__main__":
    unittest.main()
