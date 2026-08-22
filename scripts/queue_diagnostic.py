#!/usr/bin/env python3
"""Compare Anki's selected-deck queue with collection-wide due counts.

The live collection is copied with SQLite's online backup API, then only the
copy is opened by Anki. No note fields or card content are read or printed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import tempfile
import sys
import time
import types


ROOT = Path(__file__).resolve().parents[1]


def load_vellum_namespace() -> None:
    package = types.ModuleType("vellum")
    package.__path__ = [str(ROOT)]
    package.__package__ = "vellum"
    sys.modules["vellum"] = package


def queue_counts(collection: object, fetch_limit: int = 100_000) -> dict[str, int]:
    queued = collection.sched.get_queued_cards(fetch_limit=fetch_limit)
    return {
        "new": int(queued.new_count),
        "learning": int(queued.learning_count),
        "review": int(queued.review_count),
        "fetched": len(queued.cards),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("collection", type=Path)
    args = parser.parse_args()

    from anki.collection import Collection
    load_vellum_namespace()
    from vellum.anki.time_machine import collect_all_deck_queue

    with tempfile.TemporaryDirectory(prefix="vellum-queue-diagnostic-") as temp:
        snapshot = Path(temp) / "collection.anki2"
        source = sqlite3.connect(f"file:{args.collection}?mode=ro", uri=True)
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

        collection = Collection(str(snapshot))
        try:
            selected_id = int(collection.decks.get_current_id())
            selected_name = str(collection.decks.name(selected_id))
            selected = queue_counts(collection)
            started = time.perf_counter()
            all_decks = collect_all_deck_queue(collection, fetch_limit=100_000)
            all_decks_ms = (time.perf_counter() - started) * 1000
            due_review = len(collection.find_cards("is:due is:review"))
            due_learning = len(collection.find_cards("is:due is:learn"))
            due_all = len(collection.find_cards("is:due"))

            top_level: list[dict[str, object]] = []
            for deck in collection.decks.all_names_and_ids(
                skip_empty_default=False, include_filtered=False
            ):
                name = str(deck.name)
                if "::" in name:
                    continue
                deck_id = int(deck.id)
                collection.decks.set_current(deck_id)
                counts = queue_counts(collection)
                total = counts["new"] + counts["learning"] + counts["review"]
                if total:
                    top_level.append(
                        {
                            "deck_id": deck_id,
                            "deck_name": name,
                            "total": total,
                            **counts,
                        }
                    )

            print(
                json.dumps(
                    {
                        "selected_deck": {
                            "deck_id": selected_id,
                            "deck_name": selected_name,
                            **selected,
                        },
                        "vellum_all_decks": {
                            "available_cards": all_decks.available_cards,
                            "fetched_cards": len(all_decks.card_ids),
                            "active_decks": all_decks.active_decks,
                            "truncated": all_decks.truncated,
                            "elapsed_ms": round(all_decks_ms, 3),
                        },
                        "collection_due_search": {
                            "all": due_all,
                            "review": due_review,
                            "learning": due_learning,
                        },
                        "nonempty_top_level_decks": sorted(
                            top_level,
                            key=lambda item: int(item["total"]),
                            reverse=True,
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            collection.close(downgrade=False)


if __name__ == "__main__":
    main()
