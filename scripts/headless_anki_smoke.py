#!/usr/bin/env python3
"""Exercise Vellum adapters against a disposable real Anki collection.

Run this with Anki's bundled Python, from outside the repository directory, so
the repository's ``anki/`` adapter package cannot shadow Anki's own package.
The script never discovers or opens a user profile.
"""

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
    """Expose project modules without executing the add-on GUI entry point."""

    package = types.ModuleType("vellum")
    package.__path__ = [str(ROOT)]
    package.__package__ = "vellum"
    sys.modules["vellum"] = package


def main() -> None:
    from anki.collection import Collection
    from anki.decks import FilteredDeckConfig

    load_vellum_namespace()
    from vellum.anki.recovery import collect_recovery_candidates
    from vellum.anki.topic_stats import collect_topic_stats
    from vellum.core.config import RecoveryConfig
    from vellum.recovery.models import RecoveryMode
    from vellum.recovery.planner import build_recovery_plan
    from vellum.ui.recovery import unique_deck_name

    raw_tag = "Medicine::Renal::ADTKD"
    with tempfile.TemporaryDirectory(prefix="vellum-anki-smoke-") as temp_dir:
        collection_path = Path(temp_dir) / "collection.anki2"
        collection = Collection(str(collection_path))
        try:
            source_deck_id = collection.decks.id("Vellum Smoke Source")
            collection.decks.id("Vellum Smoke Recovery")
            recovery_deck_name = unique_deck_name(
                collection, "Vellum Smoke Recovery"
            )
            assert recovery_deck_name == "Vellum Smoke Recovery (2)"
            card_ids: list[int] = []
            for index in range(12):
                note = collection.new_note(collection.models.current())
                note["Front"] = f"Disposable Vellum question {index + 1}"
                note["Back"] = f"Disposable Vellum answer {index + 1}"
                note.tags = [raw_tag]
                collection.add_note(note, source_deck_id)
                card_ids.extend(card.id for card in note.cards())

            today = int(collection.sched.today)
            for index, card_id in enumerate(card_ids):
                card = collection.get_card(card_id)
                card.type = 2
                card.queue = 2
                card.ivl = 8 + index * 3
                card.due = today - (index + 1)
                card.lapses = index % 5
                card.reps = 10 + index
                collection.update_card(card)

            # Seed two legitimate review-log rows in this disposable database so
            # retention and recent-Again collection paths are exercised as well.
            now_ms = int(time.time() * 1000)
            for offset, card_id in enumerate(card_ids[:2]):
                collection.db.execute(
                    "insert into revlog "
                    "(id, cid, usn, ease, ivl, lastIvl, factor, time, type) "
                    "values (?, ?, -1, ?, 10, 8, 2500, 5000, 1)",
                    now_ms + offset,
                    card_id,
                    1 if offset == 0 else 3,
                )

            stats = collect_topic_stats(collection, raw_tag)
            result = collect_recovery_candidates(
                collection,
                raw_tag,
                current_card_id=card_ids[-1],
                recent_failure_days=14,
            )
            config = RecoveryConfig(max_quick=8, max_standard=30)
            plans = {
                mode: build_recovery_plan(
                    topic_label="ADTKD",
                    raw_tag_prefix=raw_tag,
                    mode=mode,
                    candidates=result.candidates,
                    config=config,
                )
                for mode in (
                    RecoveryMode.QUICK,
                    RecoveryMode.STANDARD,
                    RecoveryMode.FULL,
                )
            }

            quick_count = len(plans[RecoveryMode.QUICK].cards)
            standard_count = len(plans[RecoveryMode.STANDARD].cards)
            full_count = len(plans[RecoveryMode.FULL].cards)
            assert 1 <= quick_count < standard_count <= full_count == len(card_ids)
            assert all(plan.current_included for plan in plans.values())
            assert stats.total_cards == len(card_ids)
            assert stats.due_cards == len(card_ids)
            assert stats.recent_reviews == 2
            assert stats.recent_failures == 1

            selected = plans[RecoveryMode.STANDARD].card_ids
            deck = collection.sched.get_or_create_filtered_deck(0)
            deck.name = recovery_deck_name
            deck.config.reschedule = True
            del deck.config.search_terms[:]
            deck.config.search_terms.append(
                FilteredDeckConfig.SearchTerm(
                    search="cid:" + ",".join(str(card_id) for card_id in selected),
                    limit=len(selected),
                    order=4,  # LAPSES in the stable scheduler protobuf enum.
                )
            )
            operation = collection.sched.add_or_update_filtered_deck(deck)
            filtered_deck_id = int(operation.id)
            rebuilt = collection.sched.rebuild_filtered_deck(filtered_deck_id)
            filtered_ids = set(collection.find_cards("deck:filtered"))

            assert collection.decks.is_filtered(filtered_deck_id)
            assert int(rebuilt.count) == len(selected)
            assert filtered_ids == set(selected)
            assert all(
                int(collection.get_card(card_id).did) == filtered_deck_id
                and int(collection.get_card(card_id).odid) == source_deck_id
                for card_id in selected
            )

            collection.decks.remove([filtered_deck_id])
            assert not collection.find_cards("deck:filtered")
            assert all(
                int(collection.get_card(card_id).did) == source_deck_id
                and int(collection.get_card(card_id).odid) == 0
                for card_id in selected
            )

            print(
                json.dumps(
                    {
                        "anki_version": importlib.metadata.version("anki"),
                        "collection": "disposable temporary collection",
                        "topic": {
                            "cards": stats.total_cards,
                            "due": stats.due_cards,
                            "recent_reviews": stats.recent_reviews,
                            "recent_failures": stats.recent_failures,
                            "retention": stats.retention_estimate,
                            "health": stats.health_state,
                        },
                        "recovery": {
                            "eligible": len(result.candidates),
                            "excluded": result.excluded_count,
                            "quick": quick_count,
                            "standard": standard_count,
                            "full": full_count,
                            "current_card_preserved": True,
                        },
                        "filtered_deck": {
                            "created": True,
                            "rebuilt_cards": int(rebuilt.count),
                            "all_cards_returned_to_source": True,
                            "removed": True,
                            "unique_name": recovery_deck_name,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            collection.close()


if __name__ == "__main__":
    main()
