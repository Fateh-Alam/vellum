"""Versioned topic-path cache backed by the Vellum database."""

from __future__ import annotations

import json
import time
from typing import Iterable

from ..core.db import Database
from .ids import tag_signature
from .models import ParsedTopicPath


class TopicPathCache:
    def __init__(self, database: Database) -> None:
        self._database = database

    def get(
        self,
        note_id: int,
        tags: Iterable[str],
        parser_version: int,
        settings_hash: str,
    ) -> ParsedTopicPath | None:
        signature = tag_signature(tags)
        with self._database.locked() as connection:
            row = connection.execute(
                """
                SELECT result_json
                FROM topic_path_cache
                WHERE note_id = ? AND tag_signature = ?
                  AND parser_version = ? AND settings_hash = ?
                """,
                (note_id, signature, parser_version, settings_hash),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["result_json"])
            if not isinstance(payload, dict):
                return None
            return ParsedTopicPath.from_mapping(payload)
        except (json.JSONDecodeError, TypeError, ValueError):
            self.invalidate(note_id)
            return None

    def put(
        self,
        note_id: int,
        tags: Iterable[str],
        parser_version: int,
        settings_hash: str,
        result: ParsedTopicPath,
    ) -> None:
        signature = tag_signature(tags)
        payload = json.dumps(result.to_mapping(), sort_keys=True, separators=(",", ":"))
        with self._database.locked() as connection:
            try:
                connection.execute(
                    """
                INSERT INTO topic_path_cache(
                    note_id, tag_signature, parser_version, settings_hash,
                    result_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(note_id) DO UPDATE SET
                    tag_signature = excluded.tag_signature,
                    parser_version = excluded.parser_version,
                    settings_hash = excluded.settings_hash,
                    result_json = excluded.result_json,
                    updated_at = excluded.updated_at
                    """,
                    (
                    note_id,
                    signature,
                    parser_version,
                    settings_hash,
                    payload,
                    int(time.time()),
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def invalidate(self, note_id: int | None = None) -> None:
        with self._database.locked() as connection:
            try:
                if note_id is None:
                    connection.execute("DELETE FROM topic_path_cache")
                else:
                    connection.execute(
                        "DELETE FROM topic_path_cache WHERE note_id = ?", (note_id,)
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def recent_topics(self, limit: int = 12) -> tuple[ParsedTopicPath, ...]:
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    "SELECT result_json FROM topic_path_cache "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(limit * 4, 200)),),
                )
            )
        found: list[ParsedTopicPath] = []
        seen: set[str] = set()
        for row in rows:
            try:
                payload = json.loads(row["result_json"])
                parsed = ParsedTopicPath.from_mapping(payload)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if not parsed.found or not parsed.topic_id or parsed.topic_id in seen:
                continue
            seen.add(parsed.topic_id)
            found.append(parsed)
            if len(found) >= limit:
                break
        return tuple(found)
