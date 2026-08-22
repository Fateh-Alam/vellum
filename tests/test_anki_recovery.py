import unittest
from types import SimpleNamespace

from vellum.anki.recovery import collect_recovery_candidates


class FakeDB:
    def all(self, query, *args):
        card_ids = set(args[1:])
        return [(1, 4, 2)] if 1 in card_ids else []


class FakeCollection:
    def __init__(self):
        self.sched = SimpleNamespace(today=100)
        self.db = FakeDB()
        self.cards = {
            1: SimpleNamespace(
                id=1,
                nid=11,
                type=2,
                queue=2,
                due=90,
                lapses=3,
                ivl=30,
                ord=1,
                memory_state=SimpleNamespace(stability=2.5, difficulty=8.0),
            ),
            2: SimpleNamespace(
                id=2,
                nid=12,
                type=0,
                queue=0,
                due=1,
                lapses=0,
                ivl=0,
                ord=0,
                memory_state=None,
            ),
        }
        self.searches = []

    def find_cards(self, search):
        self.searches.append(search)
        return [1, 2, 3] if len(self.searches) == 1 else [1, 2]

    def get_card(self, card_id):
        return self.cards[card_id]


class RecoveryCollectionTests(unittest.TestCase):
    def test_collection_query_excludes_unavailable_and_collects_review_data(self):
        collection = FakeCollection()
        result = collect_recovery_candidates(
            collection,
            '#FirstAid::Renal "quoted"',
            current_card_id=1,
            recent_failure_days=14,
        )
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.excluded_count, 1)
        review = result.candidates[0]
        self.assertTrue(review.is_current)
        self.assertEqual(review.overdue_days, 10)
        self.assertEqual(review.recent_again_count, 2)
        self.assertEqual(review.recent_success_rate, 0.5)
        self.assertIn('-deck:filtered', collection.searches[1])
        self.assertIn('\\"quoted\\"', collection.searches[0])


if __name__ == "__main__":
    unittest.main()
