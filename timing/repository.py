"""Bounded raw timing samples plus derived robust aggregates."""

from __future__ import annotations

import statistics
import time

from ..core.db import Database
from .models import TimingBucket, TimingSummary


def trimmed_mean(values: list[int], proportion: float = 0.1) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    trim = int(len(ordered) * proportion)
    kept = ordered[trim : len(ordered) - trim] if trim else ordered
    return statistics.fmean(kept)


class TimingRepository:
    def __init__(self, database: Database, max_samples_per_bucket: int = 500) -> None:
        self._database = database
        self.max_samples_per_bucket = max_samples_per_bucket

    def add(
        self,
        bucket: TimingBucket,
        duration_ms: int,
        session_id: str | None = None,
        recorded_at: int | None = None,
    ) -> TimingSummary:
        with self._database.locked() as connection:
            now = recorded_at if recorded_at is not None else int(time.time())
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO timing_samples(bucket, duration_ms, recorded_at, "
                    "session_id) VALUES (?, ?, ?, ?)",
                    (bucket.value, duration_ms, now, session_id),
                )
                connection.execute(
                    """
                    DELETE FROM timing_samples WHERE id IN (
                        SELECT id FROM timing_samples WHERE bucket = ?
                        ORDER BY recorded_at DESC, id DESC LIMIT -1 OFFSET ?
                    )
                    """,
                    (bucket.value, self.max_samples_per_bucket),
                )
                summary = self.summary(bucket)
                connection.execute(
                    """
                    INSERT INTO timing_stats(
                        bucket, sample_count, median_ms, trimmed_mean_ms, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(bucket) DO UPDATE SET
                        sample_count=excluded.sample_count,
                        median_ms=excluded.median_ms,
                        trimmed_mean_ms=excluded.trimmed_mean_ms,
                        updated_at=excluded.updated_at
                    """,
                    (
                        bucket.value,
                        summary.sample_count,
                        summary.median_ms,
                        summary.trimmed_mean_ms,
                        now,
                    ),
                )
                connection.commit()
                return summary
            except Exception:
                connection.rollback()
                raise

    def samples(self, bucket: TimingBucket, limit: int = 500) -> list[int]:
        with self._database.locked() as connection:
            return [
                int(row[0])
                for row in connection.execute(
                    """SELECT duration_ms FROM timing_samples WHERE bucket = ?
                       ORDER BY recorded_at DESC, id DESC LIMIT ?""",
                    (bucket.value, limit),
                )
            ]

    def summary(self, bucket: TimingBucket) -> TimingSummary:
        values = self.samples(bucket)
        return TimingSummary(
            bucket,
            len(values),
            statistics.median(values) if values else None,
            trimmed_mean(values),
        )
