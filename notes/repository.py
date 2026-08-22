"""Durable, local-only topic notes that never copy Anki card text."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any

from ..core.db import Database


@dataclass(frozen=True)
class MindNote:
    id: int
    topic_id: str
    topic_label: str
    topic_path: tuple[str, ...]
    body: str
    created_at: int
    source_card_id: int | None
    last_shown_at: int | None = None
    resolved_at: int | None = None


class MindNoteRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        topic_id: str,
        topic_label: str,
        topic_path: tuple[str, ...],
        body: str,
        source_card_id: int | None,
        created_at: int | None = None,
    ) -> MindNote:
        clean_id = topic_id.strip()
        clean_body = body.strip()
        clean_label = topic_label.strip() or "Topic"
        if not clean_id:
            raise ValueError("Mind Note requires a topic")
        if not clean_body:
            raise ValueError("Mind Note cannot be empty")
        if len(clean_body) > 2_000:
            raise ValueError("Mind Note must be 2,000 characters or fewer")
        timestamp = int(time.time()) if created_at is None else int(created_at)
        with self._database.locked() as connection:
            cursor = connection.execute(
                """
                INSERT INTO mind_notes(
                    topic_id, topic_label, topic_path_json, body, created_at,
                    source_card_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_id,
                    clean_label,
                    json.dumps(list(topic_path), separators=(",", ":")),
                    clean_body,
                    timestamp,
                    source_card_id,
                ),
            )
            connection.commit()
            note_id = int(cursor.lastrowid)
        note = self.get(note_id)
        assert note is not None
        return note

    def get(self, note_id: int) -> MindNote | None:
        with self._database.locked() as connection:
            row = connection.execute(
                "SELECT * FROM mind_notes WHERE id = ?", (int(note_id),)
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def active_for_topic(
        self, topic_id: str, *, limit: int = 3
    ) -> tuple[MindNote, ...]:
        safe_limit = max(1, min(int(limit), 10))
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT * FROM mind_notes
                    WHERE topic_id = ? AND resolved_at IS NULL
                    ORDER BY created_at DESC, id DESC LIMIT ?
                    """,
                    (topic_id, safe_limit),
                )
            )
        return tuple(self._from_row(row) for row in rows)

    def recent(self, limit: int = 200) -> tuple[MindNote, ...]:
        safe_limit = max(1, min(int(limit), 500))
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    "SELECT * FROM mind_notes ORDER BY created_at DESC, id DESC LIMIT ?",
                    (safe_limit,),
                )
            )
        return tuple(self._from_row(row) for row in rows)

    def mark_shown(self, note_ids: tuple[int, ...], shown_at: int | None = None) -> None:
        if not note_ids:
            return
        timestamp = int(time.time()) if shown_at is None else int(shown_at)
        placeholders = ",".join("?" for _note_id in note_ids)
        with self._database.locked() as connection:
            connection.execute(
                f"UPDATE mind_notes SET last_shown_at = ? WHERE id IN ({placeholders})",
                (timestamp, *note_ids),
            )
            connection.commit()

    def resolve(self, note_id: int, resolved_at: int | None = None) -> bool:
        timestamp = int(time.time()) if resolved_at is None else int(resolved_at)
        with self._database.locked() as connection:
            cursor = connection.execute(
                """
                UPDATE mind_notes SET resolved_at = ?
                WHERE id = ? AND resolved_at IS NULL
                """,
                (timestamp, int(note_id)),
            )
            connection.commit()
            return bool(cursor.rowcount)

    @staticmethod
    def _from_row(row: Any) -> MindNote:
        try:
            path = json.loads(row["topic_path_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            path = []
        return MindNote(
            id=int(row["id"]),
            topic_id=str(row["topic_id"]),
            topic_label=str(row["topic_label"]),
            topic_path=tuple(item for item in path if isinstance(item, str)),
            body=str(row["body"]),
            created_at=int(row["created_at"]),
            source_card_id=(
                int(row["source_card_id"])
                if row["source_card_id"] is not None
                else None
            ),
            last_shown_at=(
                int(row["last_shown_at"])
                if row["last_shown_at"] is not None
                else None
            ),
            resolved_at=(
                int(row["resolved_at"])
                if row["resolved_at"] is not None
                else None
            ),
        )
