import unittest

from vellum.topics.health import (
    TopicHealthState,
    classify_topic_health,
    describe_topic_health,
)
from vellum.topics.models import TopicStats


class TopicHealthTests(unittest.TestCase):
    def test_insufficient_data_is_not_overclaimed(self):
        state = classify_topic_health(TopicStats(total_cards=100, recent_reviews=4))
        self.assertEqual(state, TopicHealthState.INSUFFICIENT_DATA)

    def test_states_are_textual_and_deterministic(self):
        needs = TopicStats(
            total_cards=20,
            recent_reviews=10,
            recent_failures=3,
            retention_estimate=0.7,
            due_cards=8,
        )
        strong = TopicStats(
            total_cards=20,
            recent_reviews=10,
            recent_failures=0,
            retention_estimate=1.0,
            due_cards=1,
        )
        self.assertEqual(classify_topic_health(needs), TopicHealthState.NEEDS_RECOVERY)
        self.assertEqual(classify_topic_health(strong), TopicHealthState.STRONG)

    def test_absolute_failures_do_not_penalize_a_large_healthy_sample(self):
        stats = TopicStats(
            total_cards=100,
            recent_reviews=100,
            recent_failures=5,
            retention_estimate=0.95,
            due_cards=10,
        )
        self.assertEqual(classify_topic_health(stats), TopicHealthState.STABLE)

    def test_high_due_load_with_failures_needs_recovery(self):
        stats = TopicStats(
            total_cards=20,
            recent_reviews=20,
            recent_failures=4,
            retention_estimate=0.8,
            due_cards=15,
        )
        self.assertEqual(
            classify_topic_health(stats), TopicHealthState.NEEDS_RECOVERY
        )
        reason = describe_topic_health(stats)
        self.assertIn("80% retention", reason)
        self.assertIn("15 of 20 cards are due", reason)


if __name__ == "__main__":
    unittest.main()
