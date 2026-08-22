"""Read-only Anki collection adapter for Recovery candidate gathering."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from ..recovery.models import RecoveryCandidate


STATE_BY_TYPE = {0: "new", 1: "learning", 2: "review", 3: "relearning"}


@dataclass(frozen=True)
class RecoveryQueryResult:
    candidates: tuple[RecoveryCandidate, ...]
    excluded_count: int = 0


def _search_tag(raw_prefix: str) -> str:
    escaped = raw_prefix.replace("\\", "\\\\").replace('"', '\\"')
    return f'tag:"{escaped}"'


def _chunks(values: list[int], size: int = 800) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _review_summaries(
    collection: Any, card_ids: list[int], recent_failure_days: int
) -> dict[int, tuple[int, int]]:
    cutoff_ms = int((time.time() - recent_failure_days * 86400) * 1000)
    result: dict[int, tuple[int, int]] = {}
    for card_chunk in _chunks(card_ids):
        placeholders = ",".join("?" for _ in card_chunk)
        rows = collection.db.all(
            "select cid, count(), sum(case when ease = 1 then 1 else 0 end) "
            f"from revlog where id >= ? and cid in ({placeholders}) group by cid",
            cutoff_ms,
            *card_chunk,
        )
        for cid, review_count, again_count in rows:
            result[int(cid)] = (int(review_count), int(again_count or 0))
    return result


def collect_recovery_candidates(
    collection: Any,
    raw_prefix: str,
    *,
    current_card_id: int | None,
    recent_failure_days: int,
) -> RecoveryQueryResult:
    """Gather one selected topic in a background collection operation.

    Suspended, buried, and already-filtered cards cannot safely enter another
    filtered deck, so the preview excludes them up front.
    """

    base = _search_tag(raw_prefix)
    all_ids = list(collection.find_cards(base))
    eligible_ids = list(
        collection.find_cards(f"{base} -is:suspended -is:buried -deck:filtered")
    )
    summaries = _review_summaries(
        collection, eligible_ids, recent_failure_days
    ) if eligible_ids else {}
    today = int(getattr(collection.sched, "today", 0))
    candidates: list[RecoveryCandidate] = []

    for card_id in eligible_ids:
        card = collection.get_card(card_id)
        card_type = int(getattr(card, "type", 0))
        queue = int(getattr(card, "queue", card_type))
        due = int(getattr(card, "due", 0))
        overdue = max(0, today - due) if card_type == 2 and queue == 2 else 0
        memory = getattr(card, "memory_state", None)
        reviews, agains = summaries.get(int(card_id), (0, 0))
        success_rate = (reviews - agains) / reviews if reviews else None
        candidates.append(
            RecoveryCandidate(
                card_id=int(card_id),
                note_id=int(getattr(card, "nid", 0)),
                state=STATE_BY_TYPE.get(card_type, "review"),
                lapses=max(0, int(getattr(card, "lapses", 0))),
                stability=(
                    float(memory.stability)
                    if memory is not None
                    and getattr(memory, "stability", None) is not None
                    else None
                ),
                difficulty=(
                    float(memory.difficulty)
                    if memory is not None
                    and getattr(memory, "difficulty", None) is not None
                    else None
                ),
                interval_days=max(0, int(getattr(card, "ivl", 0))),
                overdue_days=overdue,
                recent_again_count=agains,
                recent_review_count=reviews,
                recent_success_rate=success_rate,
                added_order=int(card_id),
                cloze_index=max(0, int(getattr(card, "ord", 0))),
                is_current=(
                    current_card_id is not None and int(card_id) == current_card_id
                ),
            )
        )

    return RecoveryQueryResult(
        candidates=tuple(candidates),
        excluded_count=max(0, len(all_ids) - len(eligible_ids)),
    )
