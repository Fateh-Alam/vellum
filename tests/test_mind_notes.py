from pathlib import Path
import tempfile
import unittest

from vellum.core.config import VellumConfig
from vellum.core.db import Database
from vellum.features.mind_notes import mind_note_payload, relative_age
from vellum.notes.repository import MindNoteRepository
from vellum.topics.models import CardContext


class MindNoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.directory.name) / "vellum.sqlite3")
        self.database.migrate()
        self.repository = MindNoteRepository(self.database)

    def tearDown(self) -> None:
        self.database.close()
        self.directory.cleanup()

    def test_note_lifecycle_is_topic_scoped(self) -> None:
        note = self.repository.create(
            topic_id="porphyria",
            topic_label="Porphyria",
            topic_path=("Heme", "Porphyria"),
            body="Why does rifampin worsen this?",
            source_card_id=42,
            created_at=1_000,
        )
        active = self.repository.active_for_topic("porphyria")
        self.assertEqual(active, (note,))
        self.repository.mark_shown((note.id,), shown_at=2_000)
        self.assertEqual(self.repository.get(note.id).last_shown_at, 2_000)
        self.assertTrue(self.repository.resolve(note.id, resolved_at=3_000))
        self.assertEqual(self.repository.active_for_topic("porphyria"), ())
        self.assertEqual(self.repository.recent()[0].body, note.body)

    def test_reviewer_payload_contains_note_but_never_card_text(self) -> None:
        note = self.repository.create(
            topic_id="porphyria",
            topic_label="Porphyria",
            topic_path=("Heme", "Porphyria"),
            body="My own question",
            source_card_id=42,
            created_at=100,
        )
        context = CardContext(
            card_id=42,
            note_id=9,
            deck_id=3,
            deck_name="Deck",
            raw_tags=("#Systems::Heme::Porphyria",),
            raw_topic_tag="#Systems::Heme::Porphyria",
            topic_path=("Heme", "Porphyria"),
            topic_source_root="#Systems",
            primary_topic_id="porphyria",
            ancestor_topic_ids=("heme",),
            source_badges=("Systems",),
            state="review",
            lapses=0,
            reps=2,
            due=10,
        )
        payload = mind_note_payload(context, (note,), VellumConfig(), now=100 + 3 * 86400)
        self.assertEqual(payload["notes"][0]["age"], "3 days ago")
        self.assertEqual(payload["notes"][0]["body"], "My own question")
        self.assertNotIn("cardText", payload)
        self.assertNotIn("question", payload)

    def test_relative_age_is_human_readable(self) -> None:
        self.assertEqual(relative_age(100, 100), "just now")
        self.assertEqual(relative_age(100, 100 + 3600), "1 hour ago")


if __name__ == "__main__":
    unittest.main()
