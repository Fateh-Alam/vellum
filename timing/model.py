"""State-specific robust estimates blended with current-session speed."""

from __future__ import annotations

import statistics
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping

from .models import SessionEstimate, TimingBucket
from .repository import TimingRepository


class TimingModel:
    def __init__(
        self,
        repository: TimingRepository,
        fallbacks_seconds: Mapping[TimingBucket, float],
        minimum_history: int = 20,
    ) -> None:
        self.repository = repository
        self.fallbacks_seconds = dict(fallbacks_seconds)
        self.minimum_history = minimum_history
        self._session_samples: dict[TimingBucket, deque[int]] = defaultdict(
            lambda: deque(maxlen=30)
        )

    def record(self, bucket: TimingBucket, duration_ms: int, session_id: str | None = None) -> bool:
        if duration_ms < 250 or duration_ms > 120_000:
            return False
        self.repository.add(bucket, duration_ms, session_id)
        self._session_samples[bucket].append(duration_ms)
        return True

    def estimate_seconds(self, bucket: TimingBucket) -> float:
        seconds, _using_fallback = self._estimate_and_source(bucket)
        return seconds

    def _estimate_and_source(self, bucket: TimingBucket) -> tuple[float, bool]:
        summary = self.repository.summary(bucket)
        using_fallback = (
            summary.sample_count < self.minimum_history or summary.median_ms is None
        )
        historical_ms = (
            self.fallbacks_seconds[bucket] * 1000
            if using_fallback
            else summary.median_ms
        )
        assert historical_ms is not None
        recent = self._session_samples[bucket]
        if not recent:
            return historical_ms / 1000, using_fallback
        current_ms = statistics.median(recent)
        weight = min(0.65, len(recent) / 20 * 0.65)
        seconds = ((1 - weight) * historical_ms + weight * current_ms) / 1000
        return seconds, using_fallback

    def estimate_session(self, due_order: Iterable[TimingBucket], target_seconds: float) -> SessionEstimate:
        ordered = tuple(due_order)
        estimates = {
            bucket: self._estimate_and_source(bucket) for bucket in set(ordered)
        }
        remaining = max(0.0, float(target_seconds))
        selected = 0
        used = 0.0
        counts: dict[TimingBucket, int] = defaultdict(int)
        for bucket in ordered:
            estimate = estimates[bucket][0]
            if estimate > remaining:
                break
            selected += 1
            counts[bucket] += 1
            used += estimate
            remaining -= estimate
        fallback_buckets = tuple(
            bucket for bucket in TimingBucket if bucket in estimates and estimates[bucket][1]
        )
        return SessionEstimate(
            selected,
            used,
            remaining,
            dict(counts),
            fallback_buckets,
        )

    def estimate_total_seconds(self, due_order: Iterable[TimingBucket]) -> float:
        """Estimate a full workload with no per-card database query loop."""

        ordered = tuple(due_order)
        estimates = {
            bucket: self._estimate_and_source(bucket)[0] for bucket in set(ordered)
        }
        return sum(estimates[bucket] for bucket in ordered)

    def estimate_counts_seconds(
        self, counts: Mapping[TimingBucket, int]
    ) -> float:
        """Estimate aggregate workload without materializing a large queue."""

        return sum(
            max(0, int(count)) * self.estimate_seconds(bucket)
            for bucket, count in counts.items()
            if count
        )

    def reset_session_blend(self) -> None:
        self._session_samples.clear()

    def reconfigure(
        self,
        fallbacks_seconds: Mapping[TimingBucket, float],
        minimum_history: int,
    ) -> None:
        self.fallbacks_seconds = dict(fallbacks_seconds)
        self.minimum_history = minimum_history
