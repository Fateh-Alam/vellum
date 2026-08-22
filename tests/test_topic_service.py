from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from vellum.core.config import TopicParsingConfig
from vellum.core.db import Database
from vellum.core.events import EventBus
from vellum.topics.cache import TopicPathCache
from vellum.topics.parser import TopicParser
from vellum.topics.service import TopicService


class TopicServiceTests(unittest.TestCase):
    def test_cache_tracks_tag_and_setting_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            service = TopicService(TopicParser(), TopicPathCache(database))

            first = service.resolve(7, ["Medicine::Renal::ADTKD"])
            changed_tags = service.resolve(7, ["Medicine::Cardiology::AF"])
            self.assertNotEqual(first.topic_id, changed_tags.topic_id)

            renamed_parser = TopicParser(
                replace(TopicParsingConfig(), renamed_segments={"AF": "Atrial fibrillation"})
            )
            service.reconfigure(renamed_parser)
            renamed = service.resolve(7, ["Medicine::Cardiology::AF"])
            self.assertEqual(renamed.path[-1], "Atrial fibrillation")
            database.close()

    def test_resolution_event_only_fires_on_cache_miss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            events = EventBus()
            resolved: list[int] = []
            events.subscribe("topic_resolved", lambda note_id, _result: resolved.append(note_id))
            service = TopicService(TopicParser(), TopicPathCache(database), events)
            service.resolve(12, ["Medicine::Renal"])
            service.resolve(12, ["Medicine::Renal"])
            self.assertEqual(resolved, [12])
            database.close()

    def test_corrupt_cache_entry_is_removed_and_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            service = TopicService(TopicParser(), TopicPathCache(database))
            service.resolve(4, ["Medicine::Renal"])
            database.connect().execute(
                "UPDATE topic_path_cache SET result_json = 'not json' WHERE note_id = 4"
            )
            database.connect().commit()
            result = service.resolve(4, ["Medicine::Renal"])
            self.assertEqual(result.path, ("Medicine", "Renal"))
            database.close()


if __name__ == "__main__":
    unittest.main()
