from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vellum.core.db import Database
from vellum.timing.model import TimingModel
from vellum.timing.models import TimingBucket
from vellum.timing.repository import TimingRepository, trimmed_mean


FALLBACKS = {
    TimingBucket.NEW: 20.0,
    TimingBucket.LEARNING: 12.0,
    TimingBucket.REVIEW: 7.0,
    TimingBucket.RELEARNING: 10.0,
}


class TimingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "vellum.sqlite3")
        self.db.migrate()
        self.repo = TimingRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_outliers_are_rejected_before_persistence(self) -> None:
        model = TimingModel(self.repo, FALLBACKS, minimum_history=3)
        self.assertFalse(model.record(TimingBucket.REVIEW, 100))
        self.assertFalse(model.record(TimingBucket.REVIEW, 120_001))
        self.assertEqual(self.repo.summary(TimingBucket.REVIEW).sample_count, 0)

    def test_median_resists_long_but_valid_sample(self) -> None:
        model = TimingModel(self.repo, FALLBACKS, minimum_history=3)
        for value in (6000, 7000, 100_000):
            model.record(TimingBucket.REVIEW, value)
        model.reset_session_blend()
        self.assertEqual(model.estimate_seconds(TimingBucket.REVIEW), 7.0)

    def test_fallback_is_used_until_minimum_history(self) -> None:
        model = TimingModel(self.repo, FALLBACKS, minimum_history=3)
        self.repo.add(TimingBucket.NEW, 5000)
        self.assertEqual(model.estimate_seconds(TimingBucket.NEW), 20.0)
        estimate = model.estimate_session([TimingBucket.NEW], 30)
        self.assertEqual(estimate.fallback_buckets, (TimingBucket.NEW,))

    def test_current_session_blend_increases_gradually(self) -> None:
        model = TimingModel(self.repo, FALLBACKS, minimum_history=3)
        for value in (7000, 7000, 7000):
            self.repo.add(TimingBucket.REVIEW, value)
        baseline = model.estimate_seconds(TimingBucket.REVIEW)
        model.record(TimingBucket.REVIEW, 14_000)
        blended = model.estimate_seconds(TimingBucket.REVIEW)
        self.assertGreater(blended, baseline)
        self.assertLess(blended, 14.0)

    def test_session_estimate_preserves_due_order_and_buffer(self) -> None:
        model = TimingModel(self.repo, FALLBACKS)
        estimate = model.estimate_session(
            [TimingBucket.REVIEW, TimingBucket.NEW, TimingBucket.REVIEW], 30
        )
        self.assertEqual(estimate.expected_cards, 2)
        self.assertEqual(estimate.per_bucket[TimingBucket.REVIEW], 1)
        self.assertEqual(estimate.per_bucket[TimingBucket.NEW], 1)
        self.assertEqual(estimate.remaining_buffer_seconds, 3.0)

    def test_trimmed_mean_discards_both_tails(self) -> None:
        values = [100, *([1000] * 8), 10_000]
        self.assertEqual(trimmed_mean(values), 1000.0)

    def test_large_workload_queries_each_state_summary_once(self) -> None:
        model = TimingModel(self.repo, FALLBACKS)
        buckets = [TimingBucket.REVIEW] * 5000 + [TimingBucket.NEW] * 5000
        original = self.repo.summary
        calls: list[TimingBucket] = []

        def counted(bucket: TimingBucket):
            calls.append(bucket)
            return original(bucket)

        with patch.object(self.repo, "summary", side_effect=counted):
            seconds = model.estimate_total_seconds(buckets)
        self.assertGreater(seconds, 0)
        self.assertCountEqual(calls, [TimingBucket.REVIEW, TimingBucket.NEW])

    def test_aggregate_workload_does_not_materialize_every_card(self) -> None:
        model = TimingModel(self.repo, FALLBACKS)
        seconds = model.estimate_counts_seconds(
            {TimingBucket.REVIEW: 100_000, TimingBucket.NEW: 2}
        )
        self.assertEqual(seconds, 100_000 * 7.0 + 2 * 20.0)


if __name__ == "__main__":
    unittest.main()
