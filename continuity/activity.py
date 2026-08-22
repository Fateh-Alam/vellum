"""Local profile-open activity used by Return Ramp."""

from __future__ import annotations

from dataclasses import dataclass
import time

from ..core.db import Database


@dataclass(frozen=True)
class ReturnActivity:
    opened_at: int
    previous_opened_at: int | None
    previous_closed_at: int | None
    absence_seconds: int | None


class ActivityRepository:
    """Track time away without reading Anki's profile or collection metadata."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._current: ReturnActivity | None = None
        self._ramp_claimed = False

    @property
    def current(self) -> ReturnActivity | None:
        return self._current

    def begin_open(self, opened_at: int | None = None) -> ReturnActivity:
        now = int(time.time()) if opened_at is None else int(opened_at)
        with self._database.locked() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM app_activity WHERE id = 1"
                ).fetchone()
                previous_opened = (
                    int(row["last_opened_at"]) if row is not None else None
                )
                previous_closed = (
                    int(row["last_closed_at"])
                    if row is not None and row["last_closed_at"] is not None
                    else None
                )
                away_since = previous_closed or previous_opened
                absence = (
                    max(0, now - away_since) if away_since is not None else None
                )
                connection.execute(
                    """
                    INSERT INTO app_activity(
                        id, last_opened_at, last_closed_at, open_count
                    ) VALUES (1, ?, NULL, 1)
                    ON CONFLICT(id) DO UPDATE SET
                        last_opened_at = excluded.last_opened_at,
                        last_closed_at = NULL,
                        open_count = app_activity.open_count + 1
                    """,
                    (now,),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self._current = ReturnActivity(
            opened_at=now,
            previous_opened_at=previous_opened,
            previous_closed_at=previous_closed,
            absence_seconds=absence,
        )
        self._ramp_claimed = False
        return self._current

    def finish_open(self, closed_at: int | None = None) -> None:
        if self._current is None:
            return
        now = int(time.time()) if closed_at is None else int(closed_at)
        with self._database.locked() as connection:
            connection.execute(
                "UPDATE app_activity SET last_closed_at = ? WHERE id = 1",
                (now,),
            )
            connection.commit()
        self._current = None
        self._ramp_claimed = False

    def ramp_due(self, absence_days: int) -> bool:
        absence = self._current.absence_seconds if self._current else None
        return absence is not None and absence >= max(1, absence_days) * 86400

    def claim_ramp(self, absence_days: int) -> ReturnActivity | None:
        if self._ramp_claimed or not self.ramp_due(absence_days):
            return None
        self._ramp_claimed = True
        return self._current
