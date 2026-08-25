#!/usr/bin/env python3
"""Exercise Study Builder against a disposable real Anki collection."""

from __future__ import annotations

import importlib.metadata
import json
from dataclasses import replace
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
    from vellum.anki.study_builder import (
        collect_builder_catalog,
        collect_builder_preview,
        collect_deck_tag_scope,
        collect_topic_deck_scope,
        create_builder_deck,
        exact_selection_is_current,
        rollback_builder_start,
    )
    from vellum.builder.models import (
        BuildRequest,
        BuilderDefinition,
        BuilderOrder,
        BuilderSelectionPolicy,
        BuilderWorkflow,
        StatePreset,
    )
    from vellum.core.config import TopicParsingConfig

    parent_tag = "#AK_Step1_v12::#FirstAid::14_Renal"
    with tempfile.TemporaryDirectory(prefix="vellum-builder-smoke-") as temp:
        collection = Collection(str(Path(temp) / "collection.anki2"))
        try:
            source_deck_id = int(collection.decks.id("AnKing"))
            card_ids: list[int] = []
            for index in range(9):
                note = collection.new_note(collection.models.current())
                note["Front"] = f"Disposable renal question {index + 1}"
                note["Back"] = f"Disposable renal answer {index + 1}"
                note.tags = [f"{parent_tag}::Pathology::Example_{index + 1}"]
                if index < 6:
                    note.tags.append("#AK_Step1_v12::#Pathoma::11_Kidney")
                if index < 4:
                    note.tags.append(
                        "#AK_Step1_v12::#Low/HighYield::1-HighYield"
                    )
                collection.add_note(note, source_deck_id)
                card = note.cards()[0]
                card.type = 2
                card.queue = 2
                card.ivl = 10 + index
                card.due = int(collection.sched.today) - index - 1
                card.lapses = index
                collection.update_card(card)
                card_ids.append(int(card.id))

            quota_tag = "VellumQuotaSmoke"
            for index in range(6):
                note = collection.new_note(collection.models.current())
                note["Front"] = f"Disposable quota question {index + 1}"
                note["Back"] = f"Disposable quota answer {index + 1}"
                note.tags = [quota_tag]
                collection.add_note(note, source_deck_id)
                if index >= 3:
                    card = note.cards()[0]
                    card.type = 2
                    card.queue = 2
                    card.ivl = 10
                    card.due = int(collection.sched.today) - 1
                    collection.update_card(card)

            scoped_tag = "ScopedOnly::Cardiology"
            scoped_deck_id = int(collection.decks.id("Medicine::Cardiology"))
            scoped_card_ids: list[int] = []
            for index in range(2):
                note = collection.new_note(collection.models.current())
                note["Front"] = f"Disposable scoped question {index + 1}"
                note["Back"] = f"Disposable scoped answer {index + 1}"
                note.tags = [f"{scoped_tag}::Example_{index + 1}"]
                collection.add_note(note, scoped_deck_id)
                card = note.cards()[0]
                card.type = 2
                card.queue = 2
                card.ivl = 10
                card.due = int(collection.sched.today) - 1
                collection.update_card(card)
                scoped_card_ids.append(int(card.id))

            suspended = tuple(card_ids[-2:])
            buried = card_ids[-3]
            filtered = card_ids[-4]
            collection.sched.suspend_cards(suspended)
            collection.sched.bury_cards((buried,))

            blocker_definition = BuilderDefinition(
                tags=(f"{parent_tag}::Pathology::Example_6",),
                state_preset=StatePreset.ALL,
                limit=1,
            )
            blocker_preview = collect_builder_preview(collection, blocker_definition)
            blocker = create_builder_deck(
                collection,
                BuildRequest(blocker_definition, "Vellum Other Filter"),
                blocker_preview.selected_card_ids,
            )
            assert blocker.result.card_ids == (filtered,)

            catalog = collect_builder_catalog(collection, TopicParsingConfig())
            assert parent_tag in {facet.value for facet in catalog.anking}
            topic_scope = collect_topic_deck_scope(collection, (scoped_tag,))
            topic_scope_counts = {
                node.value: node.total_count for node in topic_scope.decks
            }
            assert topic_scope_counts["Medicine"] == 2
            assert topic_scope_counts["Medicine::Cardiology"] == 2
            tag_scope = collect_deck_tag_scope(collection, ("Medicine",), catalog)
            assert tag_scope.total_count == 2
            assert any(scoped_tag in node.values for node in tag_scope.tags)
            assert not any(parent_tag in node.values for node in tag_scope.tags)
            deck_only_definition = BuilderDefinition(
                workflow=BuilderWorkflow.BROWSE_COLLECTION,
                source_decks=("Medicine",),
                include_entire_deck_scope=True,
                state_preset=StatePreset.ALL,
                limit=10,
            )
            deck_only_preview = collect_builder_preview(
                collection, deck_only_definition, catalog=catalog
            )
            assert set(deck_only_preview.selected_card_ids) == set(scoped_card_ids)
            scoped_filtered = create_builder_deck(
                collection,
                BuildRequest(deck_only_definition, "Vellum Scoped Filter"),
                (scoped_card_ids[0],),
            )
            filtered_topic_scope = collect_topic_deck_scope(collection, (scoped_tag,))
            assert {
                node.value: node.total_count for node in filtered_topic_scope.decks
            }["Medicine::Cardiology"] == 2
            collection.decks.remove([scoped_filtered.result.deck_id])
            definition = BuilderDefinition(
                topic_groups=((parent_tag,),),
                state_preset=StatePreset.ALL,
                order=BuilderOrder.MOST_LAPSES,
                limit=4,
                include_suspended=True,
            )
            preview = collect_builder_preview(
                collection,
                definition,
                generation=7,
                catalog=catalog,
            )
            assert preview.total_count == 9
            assert preview.ready_count == 5
            assert preview.suspended_count == 2
            assert preview.buried_count == 1
            assert preview.filtered_count == 1
            assert preview.selected_count == 4
            assert preview.selected_suspended_ids == suspended[::-1]
            assert exact_selection_is_current(
                collection, definition, preview.selected_card_ids
            )
            assert collect_builder_preview(
                collection, replace(definition, order=BuilderOrder.MOST_AT_RISK, limit=2)
            ).selected_count == 2
            assert collect_builder_preview(
                collection, replace(definition, order=BuilderOrder.OLDEST_SEEN, limit=2)
            ).selected_count == 2
            combined = collect_builder_preview(
                collection,
                BuilderDefinition(
                    topic_groups=(
                        (parent_tag,),
                        ("#AK_Step1_v12::#Pathoma",),
                        ("#AK_Step1_v12::#Low/HighYield::1-HighYield",),
                    ),
                    state_preset=StatePreset.ALL,
                    limit=100,
                ),
            )
            assert combined.total_count == 4
            quota_preview = collect_builder_preview(
                collection,
                BuilderDefinition(
                    tags=(quota_tag,),
                    state_preset=StatePreset.DUE_NEW,
                    limit=4,
                    selection_policy=BuilderSelectionPolicy(
                        one_card_per_note=True,
                        new_share_percent=75,
                    ),
                ),
            )
            selected_new = {
                int(card_id)
                for card_id in collection.find_cards(
                    "cid:" + ",".join(str(value) for value in quota_preview.selected_card_ids)
                    + " is:new"
                )
            }
            assert quota_preview.selected_count == 4
            assert len(selected_new) == 3

            collection.sched.unsuspend_cards(preview.selected_suspended_ids)
            request = BuildRequest(definition, "Vellum Renal Builder", generation=7)
            prepared = create_builder_deck(
                collection, request, preview.selected_card_ids
            )
            assert set(prepared.result.card_ids) == set(preview.selected_card_ids)
            assert bool(collection.decks.is_filtered(prepared.result.deck_id))

            rollback_builder_start(
                collection,
                deck_id=prepared.result.deck_id,
                deck_name=prepared.result.deck_name,
                activated_card_ids=preview.selected_suspended_ids,
            )
            assert collection.decks.name_if_exists(prepared.result.deck_id) is None
            assert set(collection.find_cards("is:suspended")) == set(suspended)

            collection.sched.unsuspend_cards(suspended)
            refreshed = collect_builder_preview(collection, definition, catalog=catalog)
            completed = create_builder_deck(
                collection,
                BuildRequest(definition, "Vellum Renal Builder"),
                refreshed.selected_card_ids,
            )
            collection.decks.select(completed.result.deck_id)
            scheduled = collection.sched.getCard()
            assert scheduled is not None
            assert int(scheduled.id) in set(completed.result.card_ids)
            review_rows_before = int(
                collection.db.scalar(
                    "select count(*) from revlog where cid = ?", scheduled.id
                )
                or 0
            )
            collection.sched.answerCard(scheduled, 3)
            answered = collection.get_card(scheduled.id)
            review_rows_after = int(
                collection.db.scalar(
                    "select count(*) from revlog where cid = ?", scheduled.id
                )
                or 0
            )
            assert review_rows_after == review_rows_before + 1
            assert int(answered.did) == source_deck_id
            assert int(answered.odid) == 0
            collection.decks.remove([completed.result.deck_id])
            assert not set(suspended).intersection(collection.find_cards("is:suspended"))
            assert all(
                int(collection.get_card(card_id).did) == source_deck_id
                for card_id in completed.result.card_ids
            )
            collection.decks.remove([blocker.result.deck_id])

            print(
                json.dumps(
                    {
                        "anki_version": importlib.metadata.version("anki"),
                        "collection": "disposable temporary collection",
                        "parent_tag_includes_descendants": preview.total_count == 9,
                        "two_path_scope": {
                            "deck_only_cards": deck_only_preview.selected_count,
                            "filtered_card_uses_home_deck": True,
                            "parent_deck_includes_subdeck": True,
                            "scoped_tags_only": True,
                        },
                        "three_tag_combination_matches": combined.total_count,
                        "selection_policy": {
                            "one_card_per_note_path": True,
                            "selected": quota_preview.selected_count,
                            "new_cards": len(selected_new),
                            "new_share_target": 75,
                        },
                        "preview": {
                            "matching": preview.total_count,
                            "ready": preview.ready_count,
                            "suspended": preview.suspended_count,
                            "buried": preview.buried_count,
                            "already_filtered": preview.filtered_count,
                            "selected": preview.selected_count,
                        },
                        "pre_study_failure": {
                            "exact_deck_removed": True,
                            "exact_activation_set_resuspended": True,
                        },
                        "normal_finish": {
                            "scheduler_answer_logged": True,
                            "cards_returned_home": True,
                            "activated_cards_remain_active": True,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            collection.close(downgrade=False)


if __name__ == "__main__":
    main()
