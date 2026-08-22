from dataclasses import replace
import unittest

from vellum.sessions.models import Session, SessionStatus
from vellum.sessions.resume import ResumeMode, ResumePlanner


def session(**changes: object) -> Session:
    base = Session(
        id="resume-1",
        started_at=100,
        last_active_at=1_000,
        status=SessionStatus.INTERRUPTED,
        deck_id=7,
        deck_name="Renal",
        reviewed_count=12,
        starting_due_count=42,
    )
    return replace(base, **changes)


class ResumePlannerTests(unittest.TestCase):
    def test_matching_fresh_queue_allows_exact_continuation(self) -> None:
        plan = ResumePlanner(clock=lambda: 2_000).assess(session(), current_due=30)
        self.assertEqual(plan.mode, ResumeMode.EXACT)
        self.assertEqual(plan.expected_remaining, 30)
        self.assertFalse(plan.stale)

    def test_changed_queue_becomes_context_resume_and_explains_new_due(self) -> None:
        plan = ResumePlanner(clock=lambda: 2_000).assess(session(), current_due=46)
        self.assertEqual(plan.mode, ResumeMode.CONTEXT)
        self.assertEqual(plan.newly_due, 16)
        self.assertIn("differs", plan.explanation)

    def test_stale_session_never_claims_exact_queue(self) -> None:
        plan = ResumePlanner(stale_after_days=7, clock=lambda: 1_000 + 8 * 86_400).assess(
            session(), current_due=30
        )
        self.assertTrue(plan.stale)
        self.assertEqual(plan.mode, ResumeMode.CONTEXT)

    def test_missing_original_counts_degrades_to_context(self) -> None:
        plan = ResumePlanner(clock=lambda: 2_000).assess(
            session(starting_due_count=None), current_due=30
        )
        self.assertEqual(plan.mode, ResumeMode.CONTEXT)
        self.assertIsNone(plan.expected_remaining)

    def test_missing_deck_identity_never_claims_exact_resume(self) -> None:
        plan = ResumePlanner(clock=lambda: 2_000).assess(
            session(deck_id=None), current_due=None
        )
        self.assertEqual(plan.mode, ResumeMode.CONTEXT)
        self.assertIn("unavailable", plan.explanation)


if __name__ == "__main__":
    unittest.main()
