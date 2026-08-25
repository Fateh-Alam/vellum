"""Ephemeral deck/topic scope contracts for the guided Study Builder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeckScopeNode:
    """One normal deck in the source tree and its inclusive match total."""

    value: str
    label: str
    path: tuple[str, ...]
    total_count: int = 0


@dataclass(frozen=True)
class ScopedTagNode:
    """One visible hierarchical tag choice present in a deck scope."""

    values: tuple[str, ...]
    label: str
    path: tuple[str, ...]
    section: str
    total_count: int
    hidden: bool = False
    badges: tuple[str, ...] = ()


@dataclass(frozen=True)
class TopicDeckScope:
    generation: int
    topics: tuple[str, ...]
    decks: tuple[DeckScopeNode, ...]
    total_count: int


@dataclass(frozen=True)
class DeckTagScope:
    generation: int
    decks: tuple[str, ...]
    tags: tuple[ScopedTagNode, ...]
    total_count: int
