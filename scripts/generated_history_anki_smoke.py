#!/usr/bin/env python3
"""Exercise generated-deck history and cleanup with a disposable Anki collection."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
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
        create_time_machine_deck,
    )
    from vellum.core.db import Database
    from vellum.sessions.generated_decks import GeneratedDeckHistoryRepository
    from vellum.sessions.manager import SessionManager
    from vellum.sessions.models import SessionOrigin
    from vellum.sessions.repository import SessionRepository

    with tempfile.TemporaryDirectory(prefix="vellum-history-smoke-") as temp:
        root = Path(temp)
        collection = Collection(str(root / "collection.anki2"))
        database = Database(root / "vellum.sqlite3")
        try:
            database.migrate()
            deck_a = int(collection.decks.id("Source A"))
            deck_b = int(collection.decks.id("Source B"))
            home: dict[int, int] = {}
            for deck_id in (deck_a, deck_b):
                for index in range(2):
                    note = collection.new_note(collection.models.current())
                    note["Front"] = f"Disposable history question {deck_id}-{index}"
                    note["Back"] = "Disposable answer"
                    collection.add_note(note, deck_id)
                    card = note.cards()[0]
                    card.type = 2
                    card.queue = 2
                    card.due = int(collection.sched.today) - 1
                    card.ivl = 10
                    collection.update_card(card)
                    home[int(card.id)] = deck_id

            snapshot = collect_all_deck_queue(collection, fetch_limit=100)
            generated = create_time_machine_deck(
                collection,
                snapshot,
                minutes=5,
                card_limit=3,
            )
            manager = SessionManager(
                SessionRepository(database), id_factory=lambda: "history-smoke"
            )
            repository = GeneratedDeckHistoryRepository(database)
            session = manager.start(
                deck_id=generated.deck_id,
                deck_name=generated.deck_name,
                query="all-decks",
                target_seconds=300,
                origin=SessionOrigin.TIME_MACHINE,
                starting_due_count=generated.card_count,
                estimated_total=generated.card_count,
            )
            first = generated.cards[0].card_id
            manager.answer_card(first, 1, 1500, None)
            manager.answer_card(first, 3, 900, None)
            # Simulate upgrading a terminal deck created by an earlier Vellum
            # build that predates generated-deck history. Startup must first
            # secure the complete manifest, then remove the exact owned deck.
            completed = manager.complete_saved(session.id)
            assert repository.backfill_sessions(collection, (completed,)) == 1
            assert collection.decks.name_if_exists(generated.deck_id) is None
            with database.locked() as connection:
                connection.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
                connection.commit()

            saved = repository.get(session.id)
            assert saved is not None
            assert saved.planned_card_count == 3
            assert len(saved.cards) == 3
            assert saved.answered_card_count == 1
            assert len(saved.answers) == 2
            assert saved.status == "completed"
            assert saved.removal_reason == "startup_terminal_cleanup"
            assert all(
                int(collection.get_card(card.card_id).did) == home[card.card_id]
                and int(collection.get_card(card.card_id).odid) == 0
                for card in generated.cards
            )
            print(
                json.dumps(
                    {
                        "collection": "disposable temporary collection",
                        "bounded_filtered_deck_cards": generated.card_count,
                        "manifest_cards": len(saved.cards),
                        "unique_answered_cards": saved.answered_card_count,
                        "answer_events": len(saved.answers),
                        "deck_removed": True,
                        "cards_returned_home": True,
                        "status": saved.status,
                        "history_survived_session_pruning": True,
                        "legacy_backfill": bool(saved.metadata["legacy_backfill"]),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            database.close()
            collection.close(downgrade=False)


if __name__ == "__main__":
    main()
