import unittest

from vellum.anki.card_context import build_card_context
from vellum.topics.parser import TopicParser
from vellum.topics.service import TopicService


class FakeDecks:
    def name(self, deck_id: int) -> str:
        return {7: "Step 1::Renal"}[deck_id]


class FakeCollection:
    decks = FakeDecks()


class FakeNote:
    id = 22
    tags = ["#AK_Step1_v13::#FirstAid::10_Renal::04_Pathology::ADTKD"]


class FakeMemoryState:
    stability = 12.5
    difficulty = 6.25


class FakeCard:
    id = 11
    nid = 22
    did = 7
    type = 2
    lapses = 3
    reps = 45
    due = 900
    memory_state = FakeMemoryState()
    col = FakeCollection()

    def note(self) -> FakeNote:
        return FakeNote()

    def current_deck_id(self) -> int:
        return self.did


class CardContextTests(unittest.TestCase):
    def test_current_card_is_converted_without_collection_scan(self) -> None:
        context = build_card_context(FakeCard(), TopicService(TopicParser()))
        self.assertEqual(context.card_id, 11)
        self.assertEqual(context.note_id, 22)
        self.assertEqual(context.deck_name, "Step 1::Renal")
        self.assertEqual(context.topic_path, ("Renal", "Pathology", "ADTKD"))
        self.assertEqual(context.state, "review")
        self.assertEqual(context.stability, 12.5)
        self.assertEqual(context.difficulty, 6.25)


if __name__ == "__main__":
    unittest.main()
