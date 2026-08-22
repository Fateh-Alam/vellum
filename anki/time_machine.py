"""Collection-wide native queue snapshots and temporary Time Machine decks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..timing.models import TimingBucket
from ..sessions.generated_decks import (
    GeneratedDeckCard,
    collect_generated_deck_cards,
)


@dataclass(frozen=True)
class AllDeckQueueSnapshot:
    """A privacy-safe scheduler snapshot across disjoint top-level decks."""

    card_ids: tuple[int, ...]
    buckets: tuple[TimingBucket, ...]
    available_cards: int
    active_decks: int
    counts: dict[TimingBucket, int]
    truncated: bool = False


@dataclass(frozen=True)
class TimeMachineDeck:
    deck_id: int
    deck_name: str
    card_count: int
    cards: tuple[GeneratedDeckCard, ...] = ()


@dataclass(frozen=True)
class TimeMachineDeckChoice:
    """One disjoint top-level deck group shown in the session picker."""

    deck_id: int
    deck_name: str
    available_cards: int
    new_cards: int
    learning_cards: int
    review_cards: int


def queued_bucket(item: Any) -> TimingBucket:
    card_type = int(getattr(item.card, "ctype", getattr(item.card, "type", 2)))
    if card_type == 3:
        return TimingBucket.RELEARNING
    if int(item.queue) == 0:
        return TimingBucket.NEW
    if int(item.queue) == 1:
        return TimingBucket.LEARNING
    return TimingBucket.REVIEW


def queued_buckets(queued: Any) -> list[TimingBucket]:
    return [queued_bucket(item) for item in queued.cards]


def _top_level_normal_decks(collection: Any) -> tuple[tuple[int, str], ...]:
    return tuple(
        sorted(
            (
                (int(deck.id), str(deck.name))
                for deck in collection.decks.all_names_and_ids(
                    skip_empty_default=False, include_filtered=False
                )
                if "::" not in str(deck.name)
            ),
            key=lambda item: item[1].casefold(),
        )
    )


def list_time_machine_decks(
    collection: Any,
) -> tuple[TimeMachineDeckChoice, ...]:
    """Return every selectable normal deck group and its current queue count."""

    original_deck_id = int(collection.decks.get_current_id())
    choices: list[TimeMachineDeckChoice] = []
    try:
        for deck_id, deck_name in _top_level_normal_decks(collection):
            collection.decks.set_current(deck_id)
            queued = collection.sched.get_queued_cards(fetch_limit=1)
            new_cards = int(queued.new_count)
            learning_cards = int(queued.learning_count)
            review_cards = int(queued.review_count)
            choices.append(
                TimeMachineDeckChoice(
                    deck_id=deck_id,
                    deck_name=deck_name,
                    available_cards=new_cards + learning_cards + review_cards,
                    new_cards=new_cards,
                    learning_cards=learning_cards,
                    review_cards=review_cards,
                )
            )
    finally:
        collection.decks.set_current(original_deck_id)
    return tuple(choices)


def collect_selected_deck_queue(
    collection: Any,
    deck_ids: tuple[int, ...] | list[int] | set[int],
    *,
    fetch_limit: int = 100_000,
) -> AllDeckQueueSnapshot:
    """Collect selected disjoint deck groups, then restore Anki's selection.

    The picker exposes top-level normal decks because they partition normal
    cards without overlap and each includes its subdecks. Suspended, buried,
    and cards already inside filtered decks remain excluded by Anki's scheduler.
    """

    limit = max(1, min(100_000, int(fetch_limit)))
    original_deck_id = int(collection.decks.get_current_id())
    card_ids: list[int] = []
    buckets: list[TimingBucket] = []
    seen: set[int] = set()
    available_cards = 0
    active_decks = 0
    counts = {bucket: 0 for bucket in TimingBucket}
    selected = {int(deck_id) for deck_id in deck_ids}
    decks = tuple(
        item for item in _top_level_normal_decks(collection) if item[0] in selected
    )

    try:
        for deck_id, _deck_name in decks:
            collection.decks.set_current(deck_id)
            remaining = max(0, limit - len(card_ids))
            queued = collection.sched.get_queued_cards(
                fetch_limit=max(1, remaining)
            )
            deck_new = int(queued.new_count)
            deck_learning = int(queued.learning_count)
            deck_review = int(queued.review_count)
            deck_total = deck_new + deck_learning + deck_review
            if not deck_total:
                continue
            active_decks += 1
            available_cards += deck_total
            counts[TimingBucket.NEW] += deck_new
            # Anki exposes learning + relearning as one aggregate count. The
            # fetched card sequence below still distinguishes them exactly.
            counts[TimingBucket.LEARNING] += deck_learning
            counts[TimingBucket.REVIEW] += deck_review
            if not remaining:
                continue
            for item in queued.cards:
                card_id = int(item.card.id)
                if card_id in seen:
                    continue
                seen.add(card_id)
                card_ids.append(card_id)
                buckets.append(queued_bucket(item))
                if len(card_ids) >= limit:
                    break
    finally:
        collection.decks.set_current(original_deck_id)

    return AllDeckQueueSnapshot(
        card_ids=tuple(card_ids),
        buckets=tuple(buckets),
        available_cards=available_cards,
        active_decks=active_decks,
        counts=counts,
        truncated=available_cards > len(card_ids),
    )


def collect_all_deck_queue(
    collection: Any, *, fetch_limit: int = 100_000
) -> AllDeckQueueSnapshot:
    """Collect every top-level normal deck once."""

    return collect_selected_deck_queue(
        collection,
        tuple(deck_id for deck_id, _name in _top_level_normal_decks(collection)),
        fetch_limit=fetch_limit,
    )


def unique_time_machine_deck_name(collection: Any, requested: str) -> str:
    candidate = requested.strip() or "Vellum Time Machine"
    if collection.decks.id_for_name(candidate) is None:
        return candidate
    suffix = 2
    while collection.decks.id_for_name(f"{candidate} ({suffix})") is not None:
        suffix += 1
    return f"{candidate} ({suffix})"


def create_time_machine_deck(
    collection: Any,
    snapshot: AllDeckQueueSnapshot,
    *,
    minutes: int,
    card_limit: int | None = None,
) -> TimeMachineDeck:
    """Build a bounded native filtered deck from the estimated queue prefix."""

    limit = len(snapshot.card_ids) if card_limit is None else max(0, int(card_limit))
    selected_card_ids = snapshot.card_ids[:limit]
    if not selected_card_ids:
        raise ValueError("No available cards remain across Anki decks")

    from anki.decks import FilteredDeckConfig  # type: ignore[import-not-found]

    name = unique_time_machine_deck_name(
        collection, f"Vellum Time Machine - {minutes} min"
    )
    deck = collection.sched.get_or_create_filtered_deck(0)
    deck.name = name
    deck.config.reschedule = True
    del deck.config.search_terms[:]
    deck.config.search_terms.append(
        FilteredDeckConfig.SearchTerm(
            search="cid:" + ",".join(str(card_id) for card_id in selected_card_ids),
            limit=len(selected_card_ids),
            order=6,  # DUE in Anki's stable filtered-deck protobuf enum.
        )
    )
    deck_id = 0
    try:
        operation = collection.sched.add_or_update_filtered_deck(deck)
        deck_id = int(operation.id)
        rebuilt = collection.sched.rebuild_filtered_deck(deck_id)
        card_count = int(rebuilt.count)
        if card_count <= 0:
            raise ValueError("Cards became unavailable before Time Machine started")
        bucket_by_card = {
            int(card_id): bucket.value
            for card_id, bucket in zip(snapshot.card_ids, snapshot.buckets)
        }
        cards = collect_generated_deck_cards(
            collection,
            deck_id,
            tuple(int(card_id) for card_id in selected_card_ids),
            buckets=bucket_by_card,
        )
        if len(cards) != card_count:
            raise ValueError("Unable to capture the complete Time Machine deck history")
    except Exception:
        if (
            deck_id
            and bool(collection.decks.is_filtered(deck_id))
            and collection.decks.name_if_exists(deck_id) == name
        ):
            collection.decks.remove([deck_id])
        raise
    return TimeMachineDeck(
        deck_id=deck_id,
        deck_name=name,
        card_count=card_count,
        cards=cards,
    )
