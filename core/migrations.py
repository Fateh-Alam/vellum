"""Ordered SQLite migrations for Vellum-owned data only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(
        version=1,
        name="initial_foundation",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at INTEGER NOT NULL,
                last_active_at INTEGER NOT NULL,
                ended_at INTEGER,
                status TEXT NOT NULL,
                deck_id INTEGER,
                deck_name TEXT,
                query TEXT,
                target_seconds INTEGER,
                origin TEXT,
                last_card_id INTEGER,
                last_topic_id TEXT,
                reviewed_count INTEGER NOT NULL DEFAULT 0,
                starting_due_count INTEGER,
                metadata_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS session_cards (
                session_id TEXT NOT NULL,
                card_id INTEGER NOT NULL,
                reviewed_at INTEGER NOT NULL,
                rating INTEGER,
                duration_ms INTEGER,
                topic_id TEXT,
                PRIMARY KEY(session_id, card_id, reviewed_at),
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS timing_stats (
                bucket TEXT PRIMARY KEY,
                sample_count INTEGER NOT NULL,
                median_ms REAL,
                trimmed_mean_ms REAL,
                updated_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS topic_cache (
                topic_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                path_json TEXT NOT NULL,
                card_ids_json TEXT,
                source_root TEXT,
                cache_version INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_topic_overrides (
                raw_value TEXT PRIMARY KEY,
                normalized_value TEXT,
                ignored INTEGER NOT NULL DEFAULT 0 CHECK (ignored IN (0, 1))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)",
            """
            CREATE INDEX IF NOT EXISTS idx_session_cards_session_reviewed
            ON session_cards(session_id, reviewed_at)
            """,
        ),
    ),
    Migration(
        version=2,
        name="topic_path_cache",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS topic_path_cache (
                note_id INTEGER PRIMARY KEY,
                tag_signature TEXT NOT NULL,
                parser_version INTEGER NOT NULL,
                settings_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_topic_path_cache_signature
            ON topic_path_cache(tag_signature, parser_version, settings_hash)
            """,
        ),
    ),
    Migration(
        version=3,
        name="timing_samples",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS timing_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bucket TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                recorded_at INTEGER NOT NULL,
                session_id TEXT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_timing_samples_bucket_time
            ON timing_samples(bucket, recorded_at DESC)
            """,
        ),
    ),
    Migration(
        version=4,
        name="session_estimated_total",
        statements=("ALTER TABLE sessions ADD COLUMN estimated_total INTEGER",),
    ),
    Migration(
        version=5,
        name="generated_deck_history",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS generated_deck_history (
                history_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                feature TEXT NOT NULL,
                deck_id INTEGER NOT NULL,
                deck_name TEXT NOT NULL,
                scope TEXT,
                target_seconds INTEGER,
                created_at INTEGER NOT NULL,
                ended_at INTEGER,
                removed_at INTEGER,
                status TEXT NOT NULL,
                removal_reason TEXT,
                planned_card_count INTEGER NOT NULL,
                answered_card_count INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS generated_deck_cards (
                history_id TEXT NOT NULL,
                card_id INTEGER NOT NULL,
                note_id INTEGER,
                original_deck_id INTEGER,
                original_deck_name TEXT,
                queue_position INTEGER NOT NULL,
                bucket TEXT,
                answered_at INTEGER,
                rating INTEGER,
                duration_ms INTEGER,
                PRIMARY KEY(history_id, card_id),
                FOREIGN KEY(history_id) REFERENCES generated_deck_history(history_id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS generated_deck_card_answers (
                history_id TEXT NOT NULL,
                card_id INTEGER NOT NULL,
                answered_at INTEGER NOT NULL,
                rating INTEGER NOT NULL,
                duration_ms INTEGER,
                PRIMARY KEY(history_id, card_id, answered_at),
                FOREIGN KEY(history_id, card_id)
                    REFERENCES generated_deck_cards(history_id, card_id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_generated_deck_history_created
            ON generated_deck_history(created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_generated_deck_cards_history_position
            ON generated_deck_cards(history_id, queue_position)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_generated_deck_answers_history_time
            ON generated_deck_card_answers(history_id, answered_at)
            """,
        ),
    ),
    Migration(
        version=6,
        name="return_ramp_backtrack_mind_notes",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS app_activity (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_opened_at INTEGER NOT NULL,
                last_closed_at INTEGER,
                open_count INTEGER NOT NULL DEFAULT 1
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mind_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id TEXT NOT NULL,
                topic_label TEXT NOT NULL,
                topic_path_json TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                source_card_id INTEGER,
                last_shown_at INTEGER,
                resolved_at INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_mind_notes_topic_active_created
            ON mind_notes(topic_id, resolved_at, created_at DESC)
            """,
        ),
    ),
    Migration(
        version=7,
        name="session_debriefs",
        statements=(
            "ALTER TABLE sessions ADD COLUMN estimated_seconds REAL",
            "ALTER TABLE session_cards ADD COLUMN topic_label TEXT",
            "ALTER TABLE session_cards ADD COLUMN topic_path_json TEXT",
            "ALTER TABLE session_cards ADD COLUMN raw_topic_tag TEXT",
            """
            CREATE TABLE IF NOT EXISTS session_debriefs (
                session_id TEXT PRIMARY KEY,
                origin TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER NOT NULL,
                unique_card_count INTEGER NOT NULL,
                answer_count INTEGER NOT NULL,
                active_duration_ms INTEGER,
                elapsed_seconds INTEGER NOT NULL,
                planned_card_count INTEGER,
                remaining_card_count INTEGER,
                target_seconds INTEGER,
                estimated_seconds REAL,
                again_count INTEGER NOT NULL DEFAULT 0,
                hard_count INTEGER NOT NULL DEFAULT 0,
                good_count INTEGER NOT NULL DEFAULT 0,
                easy_count INTEGER NOT NULL DEFAULT 0,
                pace_delta_percent REAL,
                topics_json TEXT NOT NULL DEFAULT '[]',
                mind_notes_json TEXT NOT NULL DEFAULT '[]',
                suggestion_json TEXT NOT NULL DEFAULT '{}',
                handoff_text TEXT,
                handoff_acknowledged_at INTEGER,
                completion_card_state TEXT NOT NULL DEFAULT 'none',
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS session_mind_note_events (
                session_id TEXT NOT NULL,
                note_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at INTEGER NOT NULL,
                PRIMARY KEY(session_id, note_id, event_type),
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(note_id) REFERENCES mind_notes(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_session_debriefs_created
            ON session_debriefs(created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_session_debriefs_card_state
            ON session_debriefs(completion_card_state, created_at DESC)
            """,
        ),
    ),
)
