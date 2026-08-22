from dataclasses import replace
import unittest

from vellum.core.config import RecoveryConfig
from vellum.recovery.models import (
    RecoveryCandidate,
    RecoveryCustomOptions,
    RecoveryMode,
)
from vellum.recovery.planner import build_recovery_plan
from vellum.recovery.scoring import score_candidate


def candidate(card_id: int, **changes: object) -> RecoveryCandidate:
    base = RecoveryCandidate(
        card_id=card_id,
        note_id=card_id,
        state="review",
        lapses=0,
        stability=30,
        difficulty=5,
        interval_days=10,
        overdue_days=0,
        recent_again_count=0,
        recent_review_count=3,
        recent_success_rate=1,
        added_order=card_id,
    )
    return replace(base, **changes)


class RecoveryScoringTests(unittest.TestCase):
    def test_score_is_explainable_and_deterministic(self) -> None:
        card = candidate(
            1,
            lapses=3,
            stability=2,
            overdue_days=14,
            recent_again_count=2,
            recent_review_count=4,
            recent_success_rate=0.5,
        )
        first = score_candidate(card)
        second = score_candidate(card)
        self.assertEqual(first, second)
        self.assertGreater(first.score, 10)
        self.assertTrue(any("Again" in reason for reason in first.reasons))
        self.assertTrue(any("stability" in reason for reason in first.reasons))

    def test_modes_have_increasing_scope_and_preserve_current(self) -> None:
        cards = [
            candidate(
                index,
                lapses=index % 4,
                recent_again_count=1 if index % 5 == 0 else 0,
                is_current=index == 19,
            )
            for index in range(1, 21)
        ]
        config = RecoveryConfig(max_quick=8, max_standard=12)

        def plan(mode: RecoveryMode):
            return build_recovery_plan(
                topic_label="ADTKD",
                raw_tag_prefix="Medicine::Renal::ADTKD",
                mode=mode,
                candidates=cards,
                config=config,
            )

        quick, standard, full = (
            plan(RecoveryMode.QUICK),
            plan(RecoveryMode.STANDARD),
            plan(RecoveryMode.FULL),
        )
        self.assertLess(len(quick.cards), len(standard.cards))
        self.assertLess(len(standard.cards), len(full.cards))
        self.assertTrue(quick.current_included)
        self.assertTrue(standard.current_included)
        self.assertTrue(full.current_included)

    def test_custom_filters_new_mature_and_recent_failures(self) -> None:
        cards = [
            candidate(1, state="new"),
            candidate(2, interval_days=30),
            candidate(3, recent_again_count=1),
            candidate(4),
        ]
        custom = RecoveryCustomOptions(
            card_count=10,
            include_new=False,
            include_mature=False,
            include_recently_failed=False,
            include_current=False,
        )
        plan = build_recovery_plan(
            topic_label="Topic",
            raw_tag_prefix="Topic",
            mode=RecoveryMode.CUSTOM,
            candidates=cards,
            config=RecoveryConfig(),
            custom=custom,
        )
        self.assertEqual(plan.card_ids, (4,))

    def test_suggested_starting_is_explicitly_heuristic(self) -> None:
        cards = [candidate(30), candidate(10), candidate(20)]
        plan = build_recovery_plan(
            topic_label="Topic",
            raw_tag_prefix="Topic",
            mode=RecoveryMode.FULL,
            candidates=cards,
            config=RecoveryConfig(),
        )
        self.assertTrue(all(card.suggested_starting for card in plan.cards))
        self.assertEqual(plan.card_ids, (10, 20, 30))

    def test_custom_current_card_overrides_other_exclusion_filters(self) -> None:
        cards = [
            candidate(
                1,
                interval_days=30,
                recent_again_count=1,
                is_current=True,
            ),
            candidate(2),
        ]
        plan = build_recovery_plan(
            topic_label="Topic",
            raw_tag_prefix="Topic",
            mode=RecoveryMode.CUSTOM,
            candidates=cards,
            config=RecoveryConfig(),
            custom=RecoveryCustomOptions(
                card_count=1,
                include_mature=False,
                include_recently_failed=False,
                include_current=True,
            ),
        )
        self.assertEqual(plan.card_ids, (1,))

    def test_current_new_card_is_preserved_when_new_pool_is_disabled(self) -> None:
        cards = [candidate(1, state="new", is_current=True), candidate(2)]
        for mode in (
            RecoveryMode.QUICK,
            RecoveryMode.STANDARD,
            RecoveryMode.FULL,
        ):
            plan = build_recovery_plan(
                topic_label="Topic",
                raw_tag_prefix="Topic",
                mode=mode,
                candidates=cards,
                config=RecoveryConfig(include_new=False, include_current=True),
            )
            self.assertTrue(plan.current_included, mode)


if __name__ == "__main__":
    unittest.main()
