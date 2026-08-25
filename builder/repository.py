"""Collection-scoped local persistence for dynamic Study Builder recipes."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping

from ..core.db import Database
from .models import BuilderDefinition, RecentBuilderRun, StudyRecipe


class StudyRecipeRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(
        self,
        collection_key: str,
        name: str,
        definition: BuilderDefinition,
        *,
        recipe_id: str | None = None,
        now: int | None = None,
    ) -> StudyRecipe:
        clean_name = name.strip()
        if not collection_key.strip() or not clean_name:
            raise ValueError("Study Builder recipes require a collection and name")
        now = int(time.time()) if now is None else int(now)
        recipe_id = recipe_id or uuid.uuid4().hex
        with self._database.locked() as connection:
            existing = connection.execute(
                """
                SELECT collection_key, created_at, last_run_at
                FROM study_recipes WHERE recipe_id = ?
                """,
                (recipe_id,),
            ).fetchone()
            if existing and str(existing["collection_key"]) != collection_key:
                raise ValueError("Study Builder recipe belongs to another collection")
            created_at = int(existing["created_at"]) if existing else now
            last_run = int(existing["last_run_at"]) if existing and existing["last_run_at"] is not None else None
            connection.execute(
                """
                INSERT INTO study_recipes(
                    recipe_id, collection_key, name, definition_json,
                    created_at, updated_at, last_run_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(recipe_id) DO UPDATE SET
                    name = excluded.name,
                    definition_json = excluded.definition_json,
                    updated_at = excluded.updated_at
                """,
                (
                    recipe_id,
                    collection_key,
                    clean_name,
                    definition.to_json(),
                    created_at,
                    now,
                    last_run,
                ),
            )
            connection.commit()
        saved = self.get(collection_key, recipe_id)
        assert saved is not None
        return saved

    def get(self, collection_key: str, recipe_id: str) -> StudyRecipe | None:
        with self._database.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM study_recipes
                WHERE collection_key = ? AND recipe_id = ?
                """,
                (collection_key, recipe_id),
            ).fetchone()
        return self._recipe(row) if row else None

    def list(self, collection_key: str) -> tuple[StudyRecipe, ...]:
        with self._database.locked() as connection:
            rows = connection.execute(
                """
                SELECT * FROM study_recipes WHERE collection_key = ?
                ORDER BY COALESCE(last_run_at, updated_at) DESC, name COLLATE NOCASE
                """,
                (collection_key,),
            ).fetchall()
        return tuple(self._recipe(row) for row in rows)

    def delete(self, collection_key: str, recipe_id: str) -> bool:
        with self._database.locked() as connection:
            cursor = connection.execute(
                "DELETE FROM study_recipes WHERE collection_key = ? AND recipe_id = ?",
                (collection_key, recipe_id),
            )
            connection.commit()
            return bool(cursor.rowcount)

    def mark_run(self, collection_key: str, recipe_id: str, now: int | None = None) -> bool:
        now = int(time.time()) if now is None else int(now)
        with self._database.locked() as connection:
            cursor = connection.execute(
                """
                UPDATE study_recipes SET last_run_at = ?, updated_at = updated_at
                WHERE collection_key = ? AND recipe_id = ?
                """,
                (now, collection_key, recipe_id),
            )
            connection.commit()
            return bool(cursor.rowcount)

    def add_recent(
        self,
        collection_key: str,
        definition: BuilderDefinition,
        *,
        recipe_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        now: int | None = None,
    ) -> RecentBuilderRun:
        if not collection_key.strip():
            raise ValueError("Recent Study Builder runs require a collection")
        now = int(time.time()) if now is None else int(now)
        run_id = uuid.uuid4().hex
        with self._database.locked() as connection:
            connection.execute(
                """
                INSERT INTO study_builder_recent(
                    run_id, collection_key, recipe_id, definition_json,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    collection_key,
                    recipe_id,
                    definition.to_json(),
                    json.dumps(dict(metadata or {}), separators=(",", ":")),
                    now,
                ),
            )
            connection.execute(
                """
                DELETE FROM study_builder_recent
                WHERE collection_key = ? AND run_id NOT IN (
                    SELECT run_id FROM study_builder_recent
                    WHERE collection_key = ? ORDER BY created_at DESC LIMIT 25
                )
                """,
                (collection_key, collection_key),
            )
            connection.commit()
        return RecentBuilderRun(
            run_id, collection_key, definition, recipe_id, now, dict(metadata or {})
        )

    def recent(self, collection_key: str, limit: int = 10) -> tuple[RecentBuilderRun, ...]:
        with self._database.locked() as connection:
            rows = connection.execute(
                """
                SELECT * FROM study_builder_recent WHERE collection_key = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (collection_key, max(1, min(25, int(limit)))),
            ).fetchall()
        result: list[RecentBuilderRun] = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except ValueError:
                metadata = {}
            result.append(
                RecentBuilderRun(
                    str(row["run_id"]),
                    str(row["collection_key"]),
                    BuilderDefinition.from_json(str(row["definition_json"])),
                    str(row["recipe_id"]) if row["recipe_id"] else None,
                    int(row["created_at"]),
                    metadata if isinstance(metadata, Mapping) else {},
                )
            )
        return tuple(result)

    @staticmethod
    def _recipe(row: Any) -> StudyRecipe:
        return StudyRecipe(
            recipe_id=str(row["recipe_id"]),
            collection_key=str(row["collection_key"]),
            name=str(row["name"]),
            definition=BuilderDefinition.from_json(str(row["definition_json"])),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            last_run_at=(int(row["last_run_at"]) if row["last_run_at"] is not None else None),
        )
