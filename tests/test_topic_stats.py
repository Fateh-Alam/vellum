import unittest

from vellum.anki.topic_stats import collect_topic_stats, topic_query


class FakeDatabase:
    def __init__(self) -> None:
        self.query = ""
        self.arguments: tuple[object, ...] = ()

    def first(self, query: str, *arguments: object) -> tuple[int, ...]:
        self.query = query
        self.arguments = arguments
        return (12, 1, 2, 9, 8, 4, 10, 3, 7)


class FakeScheduler:
    today = 100


class FakeCollection:
    def __init__(self) -> None:
        self.db = FakeDatabase()
        self.sched = FakeScheduler()


class TopicStatsTests(unittest.TestCase):
    def test_query_quotes_untrusted_tag_text(self) -> None:
        query = topic_query('Medicine::A "quoted" topic')
        self.assertEqual(query, 'tag:"Medicine::A \\"quoted\\" topic"')

    def test_aggregate_counts_use_one_parameterized_read(self) -> None:
        collection = FakeCollection()
        stats = collect_topic_stats(collection, "Medicine::Renal")
        self.assertEqual(stats.total_cards, 12)
        self.assertEqual(stats.mature_cards, 8)
        self.assertEqual(stats.recent_failures, 3)
        self.assertEqual(stats.recent_reviews, 10)
        self.assertEqual(stats.retention_estimate, 0.7)
        self.assertEqual(stats.health_state, "Needs Recovery")
        self.assertEqual(collection.db.query.count("?"), 5)
        self.assertEqual(collection.db.arguments[0], " medicine::renal ")
        self.assertEqual(collection.db.arguments[1], " medicine::renal::")


if __name__ == "__main__":
    unittest.main()
