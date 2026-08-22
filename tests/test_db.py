from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from vellum.core.db import Database
from vellum.core.migrations import MIGRATIONS


class DatabaseTests(unittest.TestCase):
    def test_in_memory_fallback_migrates_without_filesystem_storage(self) -> None:
        database = Database(Path(":memory:"))
        try:
            database.migrate()
            self.assertGreater(database.schema_version, 0)
        finally:
            database.close()

    def test_existing_database_can_retarget_to_ephemeral_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            database.fallback_to_memory()
            database.migrate()
            self.assertEqual(str(database.path), ":memory:")
            self.assertGreater(database.schema_version, 0)
            database.close()

    def test_initial_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            database.migrate()
            self.assertEqual(database.schema_version, 7)
            tables = {
                row[0]
                for row in database.connect().execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue(
                {
                    "schema_migrations",
                    "sessions",
                    "session_cards",
                    "timing_stats",
                    "topic_cache",
                    "user_topic_overrides",
                    "topic_path_cache",
                    "timing_samples",
                    "generated_deck_history",
                    "generated_deck_cards",
                    "generated_deck_card_answers",
                    "app_activity",
                    "mind_notes",
                    "session_debriefs",
                    "session_mind_note_events",
                }.issubset(tables)
            )
            session_columns = {
                row[1]
                for row in database.connect().execute("PRAGMA table_info(sessions)")
            }
            answer_columns = {
                row[1]
                for row in database.connect().execute("PRAGMA table_info(session_cards)")
            }
            self.assertIn("estimated_seconds", session_columns)
            self.assertTrue(
                {"topic_label", "topic_path_json", "raw_topic_tag"}.issubset(
                    answer_columns
                )
            )
            database.close()

    def test_schema_six_database_upgrades_in_place_to_schema_seven(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            connection = database.connect()
            connection.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
                """
            )
            connection.commit()
            for migration in MIGRATIONS[:6]:
                database._apply_migration(connection, migration)
            connection.execute(
                """
                INSERT INTO sessions(
                    id, started_at, last_active_at, status, origin, reviewed_count
                ) VALUES ('preserved', 1, 2, 'completed', 'normal', 1)
                """
            )
            connection.execute(
                """
                INSERT INTO session_cards(
                    session_id, card_id, reviewed_at, rating, topic_id
                ) VALUES ('preserved', 42, 2000, 1, 'legacy-topic')
                """
            )
            connection.commit()

            database.migrate()
            self.assertEqual(database.schema_version, 7)
            self.assertEqual(
                connection.execute(
                    "SELECT card_id FROM session_cards WHERE session_id = 'preserved'"
                ).fetchone()[0],
                42,
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT topic_path_json FROM session_cards WHERE session_id = 'preserved'"
                ).fetchone()[0]
            )
            database.close()

    def test_foreign_keys_cascade_session_cards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            connection = database.connect()
            connection.execute(
                """
                INSERT INTO sessions(id, started_at, last_active_at, status)
                VALUES ('session-1', 1, 1, 'active')
                """
            )
            connection.execute(
                """
                INSERT INTO session_cards(session_id, card_id, reviewed_at)
                VALUES ('session-1', 42, 2)
                """
            )
            connection.execute("DELETE FROM sessions WHERE id = 'session-1'")
            remaining = connection.execute(
                "SELECT COUNT(*) FROM session_cards"
            ).fetchone()[0]
            self.assertEqual(remaining, 0)
            database.close()

    def test_schema_does_not_attach_or_modify_anki_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vellum.sqlite3"
            database = Database(path)
            database.migrate()
            attached = database.connect().execute("PRAGMA database_list").fetchall()
            self.assertEqual(len(attached), 1)
            self.assertEqual(Path(attached[0][2]).resolve(), path.resolve())
            database.close()

    def test_repository_lock_serializes_cross_thread_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "vellum.sqlite3")
            database.migrate()
            first_entered = threading.Event()
            release_first = threading.Event()
            second_entered = threading.Event()

            def first() -> None:
                with database.locked():
                    first_entered.set()
                    release_first.wait(2)

            def second() -> None:
                first_entered.wait(2)
                with database.locked():
                    second_entered.set()

            one = threading.Thread(target=first)
            two = threading.Thread(target=second)
            one.start()
            two.start()
            self.assertTrue(first_entered.wait(1))
            self.assertFalse(second_entered.wait(0.05))
            release_first.set()
            self.assertTrue(second_entered.wait(1))
            one.join(1)
            two.join(1)
            database.close()


if __name__ == "__main__":
    unittest.main()
