"""Read-only conversion from an Anki card to Vellum's lazy CardContext."""

from __future__ import annotations

from typing import Any

from ..topics.models import CardContext
from ..topics.service import TopicService


CARD_STATES = {
    0: "new",
    1: "learning",
    2: "review",
    3: "relearning",
}


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _deck_name(card: Any, deck_id: int) -> str:
    try:
        return str(card.col.decks.name(deck_id))
    except (AttributeError, KeyError, TypeError):
        return ""


def build_card_context(card: Any, topics: TopicService) -> CardContext:
    """Resolve only the current card and never scan or mutate the collection."""

    note = card.note()
    tags = tuple(str(tag) for tag in getattr(note, "tags", ()) if str(tag).strip())
    note_id = _integer(getattr(card, "nid", getattr(note, "id", 0)))
    parsed = topics.resolve(note_id, tags)

    current_deck_id = getattr(card, "current_deck_id", None)
    deck_id = _integer(current_deck_id() if callable(current_deck_id) else card.did)
    memory_state = getattr(card, "memory_state", None)

    return CardContext(
        card_id=_integer(getattr(card, "id", 0)),
        note_id=note_id,
        deck_id=deck_id,
        deck_name=_deck_name(card, deck_id),
        raw_tags=tags,
        topic_path=parsed.path,
        topic_source_root=parsed.source_root,
        primary_topic_id=parsed.topic_id,
        ancestor_topic_ids=parsed.ancestor_topic_ids,
        source_badges=parsed.source_badges,
        state=CARD_STATES.get(_integer(getattr(card, "type", 0)), "unknown"),
        lapses=max(0, _integer(getattr(card, "lapses", 0))),
        reps=max(0, _integer(getattr(card, "reps", 0))),
        due=_integer(card.due) if getattr(card, "due", None) is not None else None,
        stability=_optional_float(getattr(memory_state, "stability", None)),
        difficulty=_optional_float(getattr(memory_state, "difficulty", None)),
        raw_topic_tag=parsed.raw_tag or None,
    )
