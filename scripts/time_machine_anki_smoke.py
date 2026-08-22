#!/usr/bin/env python3
"""Exercise collection-wide Time Machine against a disposable Anki collection."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
import time
import types


ROOT = Path(__file__).resolve().parents[1]


def load_vellum_namespace() -> None:
    package = types.ModuleType("vellum")
    package.__path__ = [str(ROOT)]
    package.__package__ = "vellum"
    sys.modules["vellum"] = package


def main() -> None:
    from anki.collection import Collection

    load_vellum_namespace()
    from vellum.anki.time_machine import (
        collect_all_deck_queue,
        collect_selected_deck_queue,
        create_time_machine_deck,
        list_time_machine_decks,
    )

    with tempfile.TemporaryDirectory(prefix="vellum-time-machine-smoke-") as temp:
        collection = Collection(str(Path(temp) / "collection.anki2"))
        try:
            deck_a = int(collection.decks.id("Alpha"))
            deck_b = int(collection.decks.id("Beta"))
            empty = int(collection.decks.id("Empty::Leaf"))
            collection.decks.id("Vellum Time Machine - 30 min")
            home_by_card: dict[int, int] = {}

            for deck_id, count in ((deck_a, 3), (deck_b, 3)):
                for index in range(count):
                    note = collection.new_note(collection.models.current())
                    note["Front"] = f"Disposable all-decks question {deck_id}-{index}"
                    note["Back"] = "Disposable answer"
                    collection.add_note(note, deck_id)
                    card = note.cards()[0]
                    card_id = int(card.id)
                    home_by_card[card_id] = deck_id
                    if deck_id == deck_a and index == 0:
                        card.type = 1
                        card.queue = 1
                        card.due = int(time.time()) - 10
                        card.left = 1001
                    elif deck_id == deck_b and index == count - 1:
                        card.type = 0
                        card.queue = 0
                    else:
                        card.type = 2
                        card.queue = 2
                        card.due = int(collection.sched.today) - 1
                        card.ivl = 10
                    collection.update_card(card)

            collection.decks.set_current(empty)
            choices = list_time_machine_decks(collection)
            assert int(collection.decks.get_current_id()) == empty
            choice_counts = {
                choice.deck_name: choice.available_cards for choice in choices
            }
            assert choice_counts["Alpha"] == 3
            assert choice_counts["Beta"] == 3
            assert choice_counts["Empty"] == 0
            assert choice_counts["Default"] == 0
            assert choice_counts["Vellum Time Machine - 30 min"] == 0
            selected_snapshot = collect_selected_deck_queue(
                collection,
                (deck_a,),
                fetch_limit=1000,
            )
            assert selected_snapshot.available_cards == 3
            assert selected_snapshot.active_decks == 1
            assert all(
                home_by_card[card_id] == deck_a
                for card_id in selected_snapshot.card_ids
            )
            selected_time_deck = create_time_machine_deck(
                collection,
                selected_snapshot,
                minutes=20,
                card_limit=2,
            )
            assert selected_time_deck.card_count == 2
            assert all(
                int(collection.get_card(card_id).odid) == deck_a
                for card_id in selected_snapshot.card_ids[:2]
            )
            collection.decks.remove([selected_time_deck.deck_id])
            assert all(
                int(collection.get_card(card_id).did) == deck_a
                and int(collection.get_card(card_id).odid) == 0
                for card_id in selected_snapshot.card_ids
            )
            collection.decks.set_current(empty)
            snapshot = collect_all_deck_queue(collection, fetch_limit=1000)
            assert int(collection.decks.get_current_id()) == empty
            assert snapshot.available_cards == 6
            assert len(snapshot.card_ids) == 6
            assert snapshot.active_decks == 2
            assert not snapshot.truncated

            time_deck = create_time_machine_deck(
                collection, snapshot, minutes=30
            )
            assert time_deck.deck_name == "Vellum Time Machine - 30 min (2)"
            assert time_deck.card_count == 6
            assert collection.decks.is_filtered(time_deck.deck_id)
            assert all(
                int(collection.get_card(card_id).did) == time_deck.deck_id
                and int(collection.get_card(card_id).odid) == home_by_card[card_id]
                for card_id in snapshot.card_ids
            )

            collection.decks.remove([time_deck.deck_id])
            assert all(
                int(collection.get_card(card_id).did) == home_by_card[card_id]
                and int(collection.get_card(card_id).odid) == 0
                for card_id in snapshot.card_ids
            )
            print(
                json.dumps(
                    {
                        "anki_version": importlib.metadata.version("anki"),
                        "scope": "all top-level normal decks",
                        "stale_empty_selection": True,
                        "available_cards": snapshot.available_cards,
                        "active_decks": snapshot.active_decks,
                        "selectable_deck_groups": len(choices),
                        "selected_deck_cards": selected_snapshot.available_cards,
                        "selected_filtered_deck_cards": selected_time_deck.card_count,
                        "filtered_deck_cards": time_deck.card_count,
                        "collision_safe_name": time_deck.deck_name,
                        "selection_restored_after_estimate": True,
                        "all_cards_returned_home": True,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            collection.close(downgrade=False)


if __name__ == "__main__":
    main()
