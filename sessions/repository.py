"""Parameterized persistence for study sessions and per-card checkpoints."""

from __future__ import annotations

import json
from typing import Any
import time

from ..core.db import Database
from .models import Session, SessionOrigin, SessionStatus, SessionTopicContext


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, session: Session) -> None:
        with self._database.locked() as connection:
            try:
                self._save_on(connection, session)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _save_on(connection: Any, session: Session) -> None:
        metadata = json.dumps(
            {"recent_topic_ids": list(session.recent_topic_ids)},
            separators=(",", ":"),
        )
        connection.execute(
            """
                INSERT INTO sessions(
                    id, started_at, last_active_at, ended_at, status, deck_id,
                    deck_name, query, target_seconds, origin, last_card_id,
                    last_topic_id, reviewed_count, starting_due_count, estimated_total,
                    estimated_seconds, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_active_at=excluded.last_active_at,
                    ended_at=excluded.ended_at,
                    status=excluded.status,
                    deck_id=excluded.deck_id,
                    deck_name=excluded.deck_name,
                    query=excluded.query,
                    target_seconds=excluded.target_seconds,
                    origin=excluded.origin,
                    last_card_id=excluded.last_card_id,
                    last_topic_id=excluded.last_topic_id,
                    reviewed_count=excluded.reviewed_count,
                    starting_due_count=excluded.starting_due_count,
                    estimated_total=excluded.estimated_total,
                    estimated_seconds=excluded.estimated_seconds,
                    metadata_json=excluded.metadata_json
            """,
            (
                session.id,
                session.started_at,
                session.last_active_at,
                session.ended_at,
                session.status.value,
                session.deck_id,
                session.deck_name,
                session.query,
                session.target_seconds,
                session.origin.value,
                session.last_card_id,
                session.last_topic_id,
                session.reviewed_count,
                session.starting_due_count,
                session.estimated_total,
                session.estimated_seconds,
                metadata,
            ),
        )

    def record_answer(
        self,
        session: Session,
        *,
        card_id: int,
        reviewed_at: int,
        rating: int,
        duration_ms: int | None,
        topic: SessionTopicContext,
    ) -> None:
        """Atomically persist one answer and its updated session checkpoint."""

        with self._database.locked() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO session_cards(
                        session_id, card_id, reviewed_at, rating, duration_ms, topic_id,
                        topic_label, topic_path_json, raw_topic_tag
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.id,
                        card_id,
                        reviewed_at,
                        rating,
                        duration_ms,
                        topic.topic_id,
                        topic.label,
                        json.dumps(list(topic.path), separators=(",", ":")),
                        topic.raw_topic_tag,
                    ),
                )
                self._save_on(connection, session)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get(self, session_id: str) -> Session | None:
        with self._database.locked() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return self._from_row(row)
        except (KeyError, TypeError, ValueError):
            self._delete_invalid(session_id)
            return None

    def latest_resumable(self) -> Session | None:
        return self._resumable_from_query(
            """
            SELECT * FROM sessions
            WHERE status IN (
                'started', 'active', 'paused', 'interrupted', 'resumed'
            )
            ORDER BY last_active_at DESC, started_at DESC, rowid DESC LIMIT 1
            """
        )

    def latest_generated_resumable(self) -> Session | None:
        return self._resumable_from_query(
            """
            SELECT * FROM sessions
            WHERE status IN (
                'started', 'active', 'paused', 'interrupted', 'resumed'
            )
              AND origin IN ('time_machine', 'recovery', 'study_builder')
            ORDER BY last_active_at DESC, started_at DESC, rowid DESC LIMIT 1
            """
        )

    def generated_resumable_for_deck(
        self, deck_id: int, deck_name: str
    ) -> Session | None:
        return self._resumable_from_query(
            """
            SELECT * FROM sessions
            WHERE status IN (
                'started', 'active', 'paused', 'interrupted', 'resumed'
            )
              AND origin IN ('time_machine', 'recovery', 'study_builder')
              AND deck_id = ? AND deck_name = ?
            ORDER BY last_active_at DESC, started_at DESC, rowid DESC LIMIT 1
            """,
            (deck_id, deck_name),
        )

    def generated_sessions(self, limit: int = 500) -> tuple[Session, ...]:
        safe_limit = max(1, min(int(limit), 5_000))
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT * FROM sessions
            WHERE origin IN ('time_machine', 'recovery', 'study_builder')
                    ORDER BY started_at, rowid
                    LIMIT ?
                    """,
                    (safe_limit,),
                )
            )
        sessions: list[Session] = []
        for row in rows:
            try:
                sessions.append(self._from_row(row))
            except (KeyError, TypeError, ValueError):
                self._delete_invalid(str(row["id"]))
        return tuple(sessions)

    def recent_terminal(self, limit: int = 200) -> tuple[Session, ...]:
        """Return retained technical session records for combined History."""

        safe_limit = max(1, min(int(limit), 500))
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT * FROM sessions
                    WHERE status IN ('completed', 'abandoned')
                    ORDER BY COALESCE(ended_at, last_active_at) DESC, rowid DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                )
            )
        sessions: list[Session] = []
        for row in rows:
            try:
                sessions.append(self._from_row(row))
            except (KeyError, TypeError, ValueError):
                self._delete_invalid(str(row["id"]))
        return tuple(sessions)

    def _resumable_from_query(
        self, query: str, arguments: tuple[Any, ...] = ()
    ) -> Session | None:
        while True:
            with self._database.locked() as connection:
                row = connection.execute(query, arguments).fetchone()
            if row is None:
                return None
            try:
                return self._from_row(row)
            except (KeyError, TypeError, ValueError):
                self._delete_invalid(str(row["id"]))

    def _delete_invalid(self, session_id: str) -> None:
        """Remove an unreadable Vellum session so Resume cannot crash launch."""

        with self._database.locked() as connection:
            try:
                connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def interrupt_open_sessions(self) -> int:
        with self._database.locked() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET status = 'interrupted'
                WHERE status IN ('started', 'active', 'paused', 'resumed')
                """
            )
            connection.commit()
            return cursor.rowcount

    def prune(self, history_days: int, maximum_sessions: int) -> int:
        """Bound only terminal history; resumable sessions are never pruned."""

        with self._database.locked() as connection:
            before = connection.total_changes
            try:
                connection.execute("BEGIN IMMEDIATE")
                if history_days > 0:
                    cutoff = int(time.time()) - history_days * 86400
                    connection.execute(
                        "DELETE FROM sessions WHERE status IN "
                        "('completed', 'abandoned') "
                        "AND COALESCE(ended_at, last_active_at) < ?",
                        (cutoff,),
                    )
                connection.execute(
                    """
                    DELETE FROM sessions WHERE id IN (
                        SELECT id FROM sessions
                        WHERE status IN ('completed', 'abandoned')
                        ORDER BY COALESCE(ended_at, last_active_at) DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (max(10, maximum_sessions),),
                )
                connection.commit()
                return connection.total_changes - before
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _from_row(row: Any) -> Session:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        recent = metadata.get("recent_topic_ids", [])
        return Session(
            id=row["id"],
            started_at=row["started_at"],
            last_active_at=row["last_active_at"],
            ended_at=row["ended_at"],
            status=SessionStatus(row["status"]),
            deck_id=row["deck_id"],
            deck_name=row["deck_name"],
            query=row["query"],
            target_seconds=row["target_seconds"],
            origin=SessionOrigin(row["origin"] or "normal"),
            last_card_id=row["last_card_id"],
            last_topic_id=row["last_topic_id"],
            reviewed_count=row["reviewed_count"],
            starting_due_count=row["starting_due_count"],
            estimated_total=row["estimated_total"],
            estimated_seconds=(
                float(row["estimated_seconds"])
                if row["estimated_seconds"] is not None
                else None
            ),
            recent_topic_ids=tuple(item for item in recent if isinstance(item, str)),
        )
