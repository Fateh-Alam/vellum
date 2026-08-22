"""Stable topic-domain models shared by Context, Recovery, and sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ParsedTopicPath:
    raw_tag: str
    source_root: str | None
    path: tuple[str, ...]
    canonical_path: tuple[str, ...]
    topic_id: str | None
    ancestor_topic_ids: tuple[str, ...] = ()
    source_badges: tuple[str, ...] = ()
    raw_prefixes: tuple[str, ...] = ()

    @property
    def found(self) -> bool:
        return bool(self.topic_id and self.path)

    @classmethod
    def empty(cls) -> "ParsedTopicPath":
        return cls("", None, (), (), None)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "raw_tag": self.raw_tag,
            "source_root": self.source_root,
            "path": list(self.path),
            "canonical_path": list(self.canonical_path),
            "topic_id": self.topic_id,
            "ancestor_topic_ids": list(self.ancestor_topic_ids),
            "source_badges": list(self.source_badges),
            "raw_prefixes": list(self.raw_prefixes),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ParsedTopicPath":
        def strings(key: str) -> tuple[str, ...]:
            value = raw.get(key)
            if not isinstance(value, list):
                return ()
            return tuple(item for item in value if isinstance(item, str))

        return cls(
            raw_tag=str(raw.get("raw_tag") or ""),
            source_root=(
                str(raw["source_root"]) if raw.get("source_root") is not None else None
            ),
            path=strings("path"),
            canonical_path=strings("canonical_path"),
            topic_id=str(raw["topic_id"]) if raw.get("topic_id") else None,
            ancestor_topic_ids=strings("ancestor_topic_ids"),
            source_badges=strings("source_badges"),
            raw_prefixes=strings("raw_prefixes"),
        )


@dataclass(frozen=True)
class CardContext:
    card_id: int
    note_id: int
    deck_id: int
    deck_name: str
    raw_tags: tuple[str, ...]
    topic_path: tuple[str, ...]
    topic_source_root: str | None
    primary_topic_id: str | None
    ancestor_topic_ids: tuple[str, ...]
    source_badges: tuple[str, ...]
    state: str
    lapses: int
    reps: int
    due: int | None
    stability: float | None = None
    difficulty: float | None = None
    recent_review_count: int = 0
    recent_fail_count: int = 0
    estimated_seconds: float | None = None
    raw_topic_tag: str | None = None


@dataclass(frozen=True)
class Topic:
    topic_id: str
    label: str
    source_root: str | None
    path: tuple[str, ...]
    parent_id: str | None = None
    child_ids: tuple[str, ...] = ()
    card_ids: tuple[int, ...] = ()
    total_cards: int = 0
    new_cards: int = 0
    learning_cards: int = 0
    review_cards: int = 0
    mature_cards: int = 0
    due_cards: int = 0
    recent_reviews: int = 0
    recent_failures: int = 0
    retention_estimate: float | None = None
    avg_stability: float | None = None
    avg_difficulty: float | None = None
    estimated_recovery_seconds: float | None = None
    health_state: str | None = None


@dataclass(frozen=True)
class TopicStats:
    total_cards: int = 0
    new_cards: int = 0
    learning_cards: int = 0
    review_cards: int = 0
    mature_cards: int = 0
    due_cards: int = 0
    recent_reviews: int = 0
    recent_failures: int = 0
    retention_estimate: float | None = None
    health_state: str | None = None
