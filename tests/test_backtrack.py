import unittest

from vellum.continuity.backtrack import BacktrackEntry, select_backtrack


def entry(card_id: int, topic_id: str) -> BacktrackEntry:
    return BacktrackEntry(
        card_id=card_id,
        shown_at=card_id,
        topic_id=topic_id,
        topic_label=topic_id,
        topic_path=(topic_id,),
        source_badges=(),
        raw_topic_tag=None,
        deck_name="Deck",
        state="review",
        lapses=0,
        reps=1,
    )


class BacktrackTests(unittest.TestCase):
    def test_previous_card_and_previous_topic_are_selected_independently(self) -> None:
        previous, previous_topic = select_backtrack(
            (entry(1, "renal"), entry(2, "cardio"), entry(3, "cardio")),
            current_card_id=3,
            current_topic_id="cardio",
        )
        self.assertEqual(previous.card_id, 2)
        self.assertEqual(previous_topic.card_id, 1)

    def test_empty_history_is_safe(self) -> None:
        self.assertEqual(
            select_backtrack((), current_card_id=7, current_topic_id=None),
            (None, None),
        )


if __name__ == "__main__":
    unittest.main()
