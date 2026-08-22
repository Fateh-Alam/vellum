"""Pure Return Ramp workload models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RampSuggestion:
    minutes: int
    expected_cards: int


@dataclass(frozen=True)
class ReturnRampWorkload:
    absence_seconds: int
    available_cards: int
    active_decks: int
    new_cards: int
    learning_cards: int
    review_cards: int
    estimated_minutes: int
    suggestions: tuple[RampSuggestion, ...]

    @property
    def absence_days(self) -> int:
        return max(0, self.absence_seconds // 86400)
