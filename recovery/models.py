"""Pure Recovery models with no Anki or Qt dependency."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecoveryMode(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"
    CUSTOM = "custom"


@dataclass(frozen=True)
class RecoveryCustomOptions:
    card_count: int = 20
    include_new: bool = False
    include_mature: bool = True
    include_recently_failed: bool = True
    include_current: bool = True
    prioritize_difficult: bool = True


@dataclass(frozen=True)
class RecoveryCandidate:
    card_id: int
    note_id: int
    state: str
    lapses: int
    stability: float | None
    difficulty: float | None
    interval_days: int
    overdue_days: int
    recent_again_count: int
    recent_review_count: int
    recent_success_rate: float | None
    added_order: int
    cloze_index: int = 0
    is_current: bool = False

    @property
    def is_new(self) -> bool:
        return self.state == "new"

    @property
    def is_mature(self) -> bool:
        return self.interval_days >= 21


@dataclass(frozen=True)
class ScoredRecoveryCard:
    candidate: RecoveryCandidate
    score: float
    reasons: tuple[str, ...]
    suggested_starting: bool = False


@dataclass(frozen=True)
class RecoveryPlan:
    topic_label: str
    raw_tag_prefix: str
    mode: RecoveryMode
    cards: tuple[ScoredRecoveryCard, ...]
    available_count: int

    @property
    def card_ids(self) -> tuple[int, ...]:
        return tuple(item.candidate.card_id for item in self.cards)

    @property
    def current_included(self) -> bool:
        return any(item.candidate.is_current for item in self.cards)
