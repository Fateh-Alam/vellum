from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TimingBucket(str, Enum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


@dataclass(frozen=True)
class TimingSummary:
    bucket: TimingBucket
    sample_count: int
    median_ms: float | None
    trimmed_mean_ms: float | None


@dataclass(frozen=True)
class SessionEstimate:
    expected_cards: int
    estimated_seconds: float
    remaining_buffer_seconds: float
    per_bucket: dict[TimingBucket, int]
    fallback_buckets: tuple[TimingBucket, ...] = ()
