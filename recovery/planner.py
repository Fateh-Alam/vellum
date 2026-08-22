"""Mode-specific, deterministic Recovery selection and ordering."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from ..core.config import RecoveryConfig
from .models import (
    RecoveryCandidate,
    RecoveryCustomOptions,
    RecoveryMode,
    RecoveryPlan,
    ScoredRecoveryCard,
)
from .scoring import score_candidate


def _weak_order(card: ScoredRecoveryCard) -> tuple[float, int, int]:
    return (-card.score, -card.candidate.recent_again_count, card.candidate.card_id)


def _suggested_starting(
    cards: Iterable[ScoredRecoveryCard], count: int = 3
) -> tuple[int, ...]:
    """Approximate broad/simple cards without claiming semantic foundations."""

    eligible = [card for card in cards if not card.candidate.is_new]
    eligible.sort(
        key=lambda card: (
            card.candidate.cloze_index,
            card.candidate.added_order,
            card.candidate.card_id,
        )
    )
    return tuple(card.candidate.card_id for card in eligible[:count])


def _mark_suggested(
    cards: Iterable[ScoredRecoveryCard], suggested: set[int]
) -> list[ScoredRecoveryCard]:
    return [
        replace(card, suggested_starting=card.candidate.card_id in suggested)
        for card in cards
    ]


def _ensure_current(
    selected: list[ScoredRecoveryCard],
    available: list[ScoredRecoveryCard],
    limit: int,
    include: bool,
) -> list[ScoredRecoveryCard]:
    if not include or any(card.candidate.is_current for card in selected):
        return selected
    current = next((card for card in available if card.candidate.is_current), None)
    if current is None:
        return selected
    if len(selected) >= limit and selected:
        selected[-1] = current
    else:
        selected.append(current)
    return selected


def build_recovery_plan(
    *,
    topic_label: str,
    raw_tag_prefix: str,
    mode: RecoveryMode,
    candidates: Iterable[RecoveryCandidate],
    config: RecoveryConfig,
    custom: RecoveryCustomOptions | None = None,
) -> RecoveryPlan:
    custom = custom or RecoveryCustomOptions()
    difficult = mode is RecoveryMode.CUSTOM and custom.prioritize_difficult
    scored = [score_candidate(card, prioritize_difficult=difficult) for card in candidates]
    scored.sort(key=_weak_order)

    include_new = custom.include_new if mode is RecoveryMode.CUSTOM else config.include_new
    available = [card for card in scored if include_new or not card.candidate.is_new]
    suggested = set(_suggested_starting(available))

    if mode is RecoveryMode.QUICK:
        weak = [card for card in available if card.score > 0]
        pool = weak or available
        limit = min(config.max_quick, len(pool))
        selected = list(pool[:limit])
        selected = _ensure_current(
            selected, scored, limit, config.include_current
        )

    elif mode is RecoveryMode.STANDARD:
        weak = [
            card
            for card in available
            if card.score >= 1 or card.candidate.recent_again_count > 0
        ]
        starters = [card for card in available if card.candidate.card_id in suggested]
        combined = starters + weak
        baseline = min(
            len(available), max(min(config.max_quick, len(available)) + 1, 8)
        )
        if len({card.candidate.card_id for card in combined}) < baseline:
            combined.extend(available[:baseline])
        selected = list(dict.fromkeys(card.candidate.card_id for card in combined))
        by_id = {card.candidate.card_id: card for card in combined}
        selected = [by_id[card_id] for card_id in selected[: config.max_standard]]
        selected = _ensure_current(
            selected, scored, config.max_standard, config.include_current
        )

    elif mode is RecoveryMode.FULL:
        starters = [card for card in available if card.candidate.card_id in suggested]
        weak = [
            card
            for card in available
            if card.candidate.card_id not in suggested
            and not card.candidate.is_current
            and not card.candidate.is_new
        ]
        current = [card for card in available if card.candidate.is_current]
        new = [card for card in available if card.candidate.is_new]
        selected = starters + weak + current + new
        selected = _ensure_current(
            selected, scored, len(selected) + 1, config.include_current
        )

    else:
        filtered = [
            card
            for card in available
            if (custom.include_mature or not card.candidate.is_mature)
            and (
                custom.include_recently_failed
                or card.candidate.recent_again_count == 0
            )
        ]
        limit = max(1, custom.card_count)
        selected = list(filtered[:limit])
        selected = _ensure_current(
            selected, scored, limit, custom.include_current
        )

    selected = _mark_suggested(selected, suggested)
    return RecoveryPlan(
        topic_label=topic_label,
        raw_tag_prefix=raw_tag_prefix,
        mode=mode,
        cards=tuple(selected),
        available_count=len(available),
    )
