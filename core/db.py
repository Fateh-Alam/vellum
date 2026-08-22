"""Vellum-owned SQLite connection and transactional migration runner."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from threading import RLock
from contextlib import contextmanager
from collections.abc import Iterator

from .migrations import MIGRATIONS, Migration


class Database:
    """Thread-safe owner of the separate Vellum database file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                if str(self.path) != ":memory:":
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(
                    str(self.path), check_same_thread=False
                )
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA busy_timeout = 5000")
                self._connection = connection
            return self._connection

    @contextmanager
    def locked(self) -> Iterator[sqlite3.Connection]:
        """Serialize complete repository operations on the shared connection."""

        with self._lock:
            yield self.connect()

    def migrate(self) -> None:
        with self._lock:
            connection = self.connect()
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in MIGRATIONS:
                if migration.version not in applied:
                    self._apply_migration(connection, migration)

    @staticmethod
    def _apply_migration(
        connection: sqlite3.Connection, migration: Migration
    ) -> None:
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @property
    def schema_version(self) -> int:
        with self.locked() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()
            return int(row["version"] if row else 0)

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def fallback_to_memory(self) -> None:
        """Disconnect from failed storage and continue with an ephemeral DB."""

        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self.path = Path(":memory:")

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
