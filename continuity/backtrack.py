"""In-memory, content-free Backtrack checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BacktrackEntry:
    card_id: int
    shown_at: int
    topic_id: str | None
    topic_label: str | None
    topic_path: tuple[str, ...]
    source_badges: tuple[str, ...]
    raw_topic_tag: str | None
    deck_name: str
    state: str
    lapses: int
    reps: int


def select_backtrack(
    entries: Iterable[BacktrackEntry],
    *,
    current_card_id: int,
    current_topic_id: str | None,
) -> tuple[BacktrackEntry | None, BacktrackEntry | None]:
    """Select the last different card and last different topic context."""

    history = tuple(entries)
    previous = next(
        (
            entry
            for entry in reversed(history)
            if entry.card_id != current_card_id
        ),
        None,
    )
    previous_topic = next(
        (
            entry
            for entry in reversed(history)
            if entry.card_id != current_card_id
            and entry.topic_id
            and entry.topic_id != current_topic_id
        ),
        previous,
    )
    return previous, previous_topic
