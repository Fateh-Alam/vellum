import tempfile
import unittest
from pathlib import Path

from vellum.core.config import VellumConfig
from vellum.core.db import Database
from vellum.core.diagnostics import (
    build_diagnostics,
    clear_mind_note_data,
    clear_vellum_data,
    recent_problem_logs,
)


class DiagnosticsTests(unittest.TestCase):
    def test_export_redacts_user_topic_configuration_and_card_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(root / "vellum.sqlite3")
            database.migrate()
            log = root / "vellum.log"
            log.write_text("2026 WARNING card_id=123 failed\ncard text secret\n")
            payload = build_diagnostics(
                config=VellumConfig(),
                database=database,
                log_path=log,
                anki_version="test",
            )
            self.assertNotIn("preferred_roots", payload["config"]["topic_parsing"])
            self.assertNotIn("123", "".join(payload["recent_problem_logs"]))
            self.assertNotIn("card text secret", str(payload))

    def test_reset_rejects_non_vellum_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            with self.assertRaises(ValueError):
                clear_vellum_data(database, ("cards",))

    def test_clearing_mind_notes_redacts_durable_debrief_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            connection = database.connect()
            connection.execute(
                """
                INSERT INTO session_debriefs(
                    session_id, origin, status, started_at, ended_at,
                    unique_card_count, answer_count, elapsed_seconds,
                    again_count, hard_count, good_count, easy_count,
                    topics_json, mind_notes_json, suggestion_json,
                    completion_card_state, created_at
                ) VALUES (
                    'private', 'normal', 'completed', 1, 2,
                    0, 0, 1, 0, 0, 0, 0,
                    '[]', '[{"body":"private note"}]', '{}', 'none', 2
                )
                """
            )
            connection.commit()
            clear_mind_note_data(database)
            saved = connection.execute(
                "SELECT mind_notes_json FROM session_debriefs WHERE session_id = 'private'"
            ).fetchone()[0]
            self.assertEqual(saved, "[]")
            database.close()


if __name__ == "__main__":
    unittest.main()
