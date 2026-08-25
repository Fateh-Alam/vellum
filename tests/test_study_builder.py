from pathlib import Path
import tempfile
import unittest

from vellum.builder.catalog import build_catalog
from vellum.builder.models import (
    BuilderDefinition,
    BuilderFilterGroup,
    BuilderOrder,
    BuilderQuickFilters,
    BuilderSelectionPolicy,
    BuilderSelector,
    BuilderWorkflow,
    CardMaturity,
    FilterOperator,
    StatePreset,
)
from vellum.builder.query import availability_query, compile_builder_query
from vellum.builder.repository import StudyRecipeRepository
from vellum.core.db import Database
from vellum.anki.study_builder import (
    collect_builder_preview,
    exact_selection_is_current,
)
from vellum.features.study_builder import StudyBuilderModule
from vellum.ui.study_builder import _pruned_hierarchy


class StudyBuilderQueryTests(unittest.TestCase):
    def test_v3_topic_and_deck_scopes_compile_or_within_and_across(self) -> None:
        definition = BuilderDefinition(
            workflow=BuilderWorkflow.FIND_TOPICS,
            topic_tags=("Systems::Renal", "Systems::Cardiology"),
            source_decks=("AnKing", "Medicine::Year 3"),
            state_preset=StatePreset.ALL,
        )
        query = compile_builder_query(definition)
        self.assertEqual(
            query,
            '(tag:"Systems::Renal" or tag:"Systems::Cardiology") '
            '(deck:"AnKing" or deck:"Medicine::Year 3")',
        )
        restored = BuilderDefinition.from_json(definition.to_json())
        self.assertEqual(restored.definition_version, 3)
        self.assertEqual(restored.workflow, BuilderWorkflow.FIND_TOPICS)
        self.assertEqual(restored.topic_tags, definition.topic_tags)
        self.assertEqual(restored.source_decks, definition.source_decks)

    def test_simple_v2_recipe_maps_losslessly_to_guided_v3(self) -> None:
        value = BuilderDefinition.from_mapping(
            {
                "definition_version": 2,
                "filter_groups": [
                    {
                        "group_id": "topics",
                        "operator": "any",
                        "selectors": [
                            {"kind": "tag", "value": "Renal"},
                            {"kind": "tag", "value": "Cardiology"},
                        ],
                    },
                    {
                        "group_id": "decks",
                        "operator": "any",
                        "selectors": [
                            {"kind": "deck", "value": "AnKing"},
                        ],
                    },
                ],
                "state_preset": "all",
            }
        )
        self.assertEqual(value.definition_version, 3)
        self.assertEqual(value.topic_tags, ("Renal", "Cardiology"))
        self.assertEqual(value.source_decks, ("AnKing",))
        self.assertFalse(value.filter_groups)
        self.assertEqual(
            compile_builder_query(value),
            '(tag:"Renal" or tag:"Cardiology") deck:"AnKing"',
        )

    def test_nonmappable_v2_recipe_preserves_exact_legacy_groups(self) -> None:
        value = BuilderDefinition.from_mapping(
            {
                "definition_version": 2,
                "filter_groups": [
                    {
                        "group_id": "renal",
                        "operator": "all",
                        "selectors": [{"kind": "tag", "value": "Renal"}],
                    },
                    {
                        "group_id": "yield",
                        "operator": "all",
                        "selectors": [{"kind": "tag", "value": "High Yield"}],
                    },
                ],
                "state_preset": "all",
            }
        )
        self.assertEqual(value.definition_version, 2)
        self.assertEqual(len(value.filter_groups), 2)
        self.assertEqual(
            compile_builder_query(value),
            'tag:"Renal" tag:"High Yield"',
        )

    def test_selecting_hierarchy_node_replaces_redundant_ancestor_or_child(self) -> None:
        self.assertEqual(
            _pruned_hierarchy({"AnKing"}, ("AnKing::Step 1",)),
            {"AnKing::Step 1"},
        )
        self.assertEqual(
            _pruned_hierarchy(
                {"AnKing::Step 1", "AnKing::Step 2"}, ("AnKing",)
            ),
            {"AnKing"},
        )

    def test_explicit_groups_and_quick_filters_compile_predictably(self) -> None:
        definition = BuilderDefinition(
            filter_groups=(
                BuilderFilterGroup(
                    "renal",
                    FilterOperator.ALL,
                    (BuilderSelector("tag", "Systems::Renal"),),
                ),
                BuilderFilterGroup(
                    "resources",
                    FilterOperator.ANY,
                    (
                        BuilderSelector("tag", "Pathoma"),
                        BuilderSelector("tag", "B&B"),
                    ),
                ),
            ),
            quick_filters=BuilderQuickFilters(
                recent_again_days=7,
                added_days=30,
                marked=True,
                maturity=CardMaturity.MATURE,
            ),
            state_preset=StatePreset.NEW,
        )
        query = compile_builder_query(definition)
        self.assertIn('tag:"Systems::Renal"', query)
        self.assertIn('(tag:"Pathoma" or tag:"B&B")', query)
        self.assertIn("is:new", query)
        self.assertIn("rated:7:1", query)
        self.assertIn("added:30", query)
        self.assertIn("tag:marked", query)
        self.assertIn("prop:ivl>=21", query)

    def test_legacy_definition_is_upgraded_without_changing_meaning(self) -> None:
        old = {
            "tags": ["Pathoma", "B&B"],
            "topic_groups": [["Systems::Renal"], ["High Yield"]],
            "state_preset": "recent_failures",
            "limit": 100,
        }
        upgraded = BuilderDefinition.from_mapping(old)
        self.assertEqual(upgraded.definition_version, 2)
        self.assertFalse(upgraded.tags)
        self.assertEqual(upgraded.state_preset, StatePreset.ALL)
        self.assertEqual(upgraded.quick_filters.recent_again_days, 7)
        query = compile_builder_query(upgraded)
        self.assertIn('(tag:"Pathoma" or tag:"B&B")', query)
        self.assertIn('tag:"Systems::Renal"', query)
        self.assertIn('tag:"High Yield"', query)
        self.assertIn("rated:7:1", query)

    def test_facets_or_within_group_and_across_groups(self) -> None:
        definition = BuilderDefinition(
            text_query='heart failure',
            decks=("AnKing", "Clinical Medicine"),
            topic_groups=(("#AK_Step1_v12::#FirstAid::07_Cardiovascular",),),
            tags=("High Yield", "Needs Review"),
            excluded_tags=("!DELETE(Duplicate)",),
            note_types=("AnKingOverhaul",),
            flags=(1, 3),
            state_preset=StatePreset.DUE_NEW,
        )
        query = compile_builder_query(definition)
        self.assertIn("(heart failure)", query)
        self.assertIn('(deck:"AnKing" or deck:"Clinical Medicine")', query)
        self.assertIn('tag:"#AK_Step1_v12::#FirstAid::07_Cardiovascular"', query)
        self.assertIn('(tag:"High Yield" or tag:"Needs Review")', query)
        self.assertIn('-tag:"!DELETE(Duplicate)"', query)
        self.assertIn('(flag:1 or flag:3)', query)
        self.assertTrue(query.endswith("(is:due or is:new)"))

    def test_easy_tag_combinations_narrow_with_and(self) -> None:
        definition = BuilderDefinition(
            topic_groups=(
                ("#AK_Step1_v12::#FirstAid::14_Renal",),
                ("#AK_Step1_v12::#Pathoma",),
                ("#AK_Step1_v12::#Low/HighYield::1-HighYield",),
            ),
            state_preset=StatePreset.ALL,
        )
        query = compile_builder_query(definition)
        self.assertEqual(query.count('tag:"'), 3)
        self.assertNotIn(" or ", query)
        self.assertIn('tag:"#AK_Step1_v12::#FirstAid::14_Renal"', query)
        self.assertIn('tag:"#AK_Step1_v12::#Pathoma"', query)

    def test_advanced_query_replaces_plain_text_only(self) -> None:
        definition = BuilderDefinition(
            text_query="ignored",
            advanced_query='rated:30:1 prop:lapses>2',
            decks=("Renal",),
            state_preset=StatePreset.ALL,
        )
        query = compile_builder_query(definition)
        self.assertNotIn("ignored", query)
        self.assertIn("(rated:30:1 prop:lapses>2)", query)
        self.assertIn('deck:"Renal"', query)

    def test_quotes_and_backslashes_are_escaped(self) -> None:
        query = compile_builder_query(
            BuilderDefinition(tags=('A "quoted" \\ tag',), state_preset=StatePreset.ALL)
        )
        self.assertEqual(query, 'tag:"A \\"quoted\\" \\\\ tag"')

    def test_availability_buckets_are_explicit(self) -> None:
        self.assertEqual(
            availability_query("is:new", "ready"),
            "is:new -is:suspended -is:buried -deck:filtered",
        )
        self.assertEqual(
            availability_query("is:new", "selectable", include_suspended=True),
            "is:new -is:buried -deck:filtered",
        )

    def test_definition_round_trip_and_bounds(self) -> None:
        definition = BuilderDefinition(
            tags=("Renal",),
            topic_groups=(("Systems::Renal", "Subjects::Renal"), ("High Yield",)),
            state_preset=StatePreset.RECENT_FAILURES,
            order=BuilderOrder.MOST_LAPSES,
            limit=321,
            include_suspended=True,
        )
        self.assertEqual(BuilderDefinition.from_json(definition.to_json()), definition)
        with self.assertRaises(ValueError):
            BuilderDefinition(limit=0)

    def test_stale_exact_selection_is_rejected(self) -> None:
        class Collection:
            current = (11, 12)

            def find_cards(self, query: str) -> tuple[int, ...]:
                self.last_query = query
                return self.current

        collection = Collection()
        definition = BuilderDefinition(tags=("Renal",), state_preset=StatePreset.ALL)
        self.assertTrue(exact_selection_is_current(collection, definition, (11, 12)))
        self.assertIn("cid:11,12", collection.last_query)
        collection.current = (11,)
        self.assertFalse(exact_selection_is_current(collection, definition, (11, 12)))

    def test_preview_reuses_availability_results_for_selection(self) -> None:
        class Scheduler:
            today = 100

        class Collection:
            sched = Scheduler()

            def __init__(self) -> None:
                self.queries: list[str] = []

            def find_cards(self, query: str, order: object = False) -> tuple[int, ...]:
                self.queries.append(query)
                if query.endswith(" is:suspended -is:buried -deck:filtered"):
                    return (2,)
                if query.endswith(" is:buried"):
                    return (3,)
                if query.endswith(" deck:filtered"):
                    return (4,)
                if query.endswith(" -is:suspended -is:buried -deck:filtered"):
                    return (1,)
                return (1, 2, 3, 4)

        collection = Collection()
        preview = collect_builder_preview(
            collection,
            BuilderDefinition(
                tags=("Renal",),
                state_preset=StatePreset.ALL,
                limit=2,
                include_suspended=True,
            ),
            show_snippets=False,
            snippet_limit=0,
        )
        self.assertEqual(len(collection.queries), 5)
        self.assertEqual(preview.selected_card_ids, (1, 2))
        self.assertEqual(preview.selected_suspended_ids, (2,))

    def test_sibling_avoidance_and_due_new_share_shape_exact_selection(self) -> None:
        class Scheduler:
            today = 100

        class Database:
            def all(self, _query: str, *card_ids: int) -> tuple[tuple[int, int], ...]:
                note_ids = {1: 10, 2: 10, 3: 30, 4: 40, 5: 50, 6: 60}
                return tuple((card_id, note_ids[card_id]) for card_id in card_ids)

        class Collection:
            sched = Scheduler()
            db = Database()

            def find_cards(self, query: str, order: object = False) -> tuple[int, ...]:
                if query.startswith("(") and query.endswith(") is:new"):
                    return (1, 2, 3)
                if " is:suspended -is:buried -deck:filtered" in query:
                    return ()
                if query.endswith(" is:buried") or query.endswith(" deck:filtered"):
                    return ()
                if query.endswith("-is:suspended -is:buried -deck:filtered"):
                    return (1, 2, 3, 4, 5, 6)
                return (1, 2, 3, 4, 5, 6)

        preview = collect_builder_preview(
            Collection(),
            BuilderDefinition(
                tags=("Renal",),
                state_preset=StatePreset.DUE_NEW,
                limit=4,
                selection_policy=BuilderSelectionPolicy(
                    one_card_per_note=True,
                    new_share_percent=50,
                ),
            ),
            show_snippets=False,
            snippet_limit=0,
        )
        self.assertEqual(preview.selected_card_ids, (1, 3, 4, 5))

    def test_zero_results_identify_a_removable_group(self) -> None:
        class Scheduler:
            today = 100

        class Collection:
            sched = Scheduler()

            def find_cards(self, query: str, order: object = False) -> tuple[int, ...]:
                return () if "High Yield" in query else (1, 2)

        preview = collect_builder_preview(
            Collection(),
            BuilderDefinition(
                filter_groups=(
                    BuilderFilterGroup(
                        "renal",
                        selectors=(BuilderSelector("tag", "Renal"),),
                    ),
                    BuilderFilterGroup(
                        "yield",
                        selectors=(BuilderSelector("tag", "High Yield"),),
                    ),
                ),
                state_preset=StatePreset.ALL,
            ),
            show_snippets=False,
            snippet_limit=0,
        )
        self.assertIsNotNone(preview.diagnostic)
        self.assertEqual(preview.diagnostic.remove_group_id, "yield")
        self.assertIn("2 ready", preview.diagnostic.message)

    def test_zero_results_offer_safe_resource_regrouping(self) -> None:
        first_aid = "#AK_Step1_v12::#FirstAid::07_Cardiovascular"
        sketchy = "#AK_Step1_v12::#Sketchy::Cardiovascular"
        catalog = build_catalog(deck_names=(), tags=(first_aid, sketchy))

        class Scheduler:
            today = 100

        class Collection:
            sched = Scheduler()

            def find_cards(self, query: str, order: object = False) -> tuple[int, ...]:
                return (1, 2, 3) if " or " in query and "-is:suspended" in query else ()

        preview = collect_builder_preview(
            Collection(),
            BuilderDefinition(
                filter_groups=(
                    BuilderFilterGroup(
                        "first-aid",
                        selectors=(BuilderSelector("tag", first_aid),),
                    ),
                    BuilderFilterGroup(
                        "sketchy",
                        selectors=(BuilderSelector("tag", sketchy),),
                    ),
                ),
                state_preset=StatePreset.ALL,
            ),
            catalog=catalog,
            show_snippets=False,
            snippet_limit=0,
        )
        self.assertIsNotNone(preview.diagnostic)
        self.assertEqual(
            preview.diagnostic.merge_group_ids,
            ("first-aid", "sketchy"),
        )
        self.assertEqual(preview.diagnostic.action_label, "Match as alternatives")

class StudyBuilderCatalogTests(unittest.TestCase):
    def test_guided_topic_search_never_returns_decks_or_card_objects(self) -> None:
        catalog = build_catalog(
            deck_names=("Renal",),
            tags=("Systems::Renal",),
            note_types=("Renal",),
            card_types=("Renal",),
        )
        matches = catalog.search_topics("renal", limit=20)
        self.assertTrue(matches)
        self.assertTrue(all(facet.kind in {"topic", "tag"} for facet in matches))
        self.assertNotIn("deck", {facet.kind for facet in matches})

    def test_anking_v12_facets_and_generic_topics(self) -> None:
        catalog = build_catalog(
            deck_names=("AnKing", "Medicine::Renal"),
            tags=(
                "#AK_Step1_v12::#FirstAid::14_Renal::Pathology::ADTKD",
                "#AK_Step1_v12::#Low/HighYield::1-HighYield",
                "#AK_Step1_v12::^Systems::Renal",
                "#AK_Step2_v12::#Subjects::Internal_Medicine::Cardiology",
                "Medicine::Renal::Tubulointerstitial::ADTKD",
                "FlatTag",
                "!DELETE(Duplicate)",
            ),
            note_types=("Basic", "Cloze"),
            card_types=("Card 1", "Cloze"),
        )
        self.assertTrue(catalog.has_anking)
        groups = {facet.group for facet in catalog.anking}
        self.assertTrue({"Exam", "Resources", "Yield", "Systems"}.issubset(groups))
        self.assertIn(
            "#AK_Step1_v12::#FirstAid::14_Renal",
            {facet.value for facet in catalog.anking},
        )
        self.assertIn(
            "Medicine::Renal::Tubulointerstitial::ADTKD",
            {facet.value for facet in catalog.topics},
        )
        high_yield = next(
            facet
            for facet in catalog.anking
            if facet.value.endswith("::1-HighYield")
        )
        self.assertEqual(high_yield.path, ("Yield", "High Yield"))
        delete = next(facet for facet in catalog.tags if facet.value == "!DELETE(Duplicate)")
        self.assertTrue(delete.hidden)

    def test_indexed_search_prefers_human_facing_paths(self) -> None:
        catalog = build_catalog(
            deck_names=("AnKing", "Medicine::Renal"),
            tags=(
                "#AK_Step1_v12::#FirstAid::14_Renal::Pathology::ADTKD",
                "#AK_Step1_v12::#Low/HighYield::1-HighYield",
                "#AK_Step1_v12::#Pathoma::Renal",
                "#AK_Step1_v12::#FirstAid::$AnkiHub::Cardiovascular",
                "!DELETE(Duplicate)",
            ),
            note_types=("Basic", "Cloze"),
        )

        renal = catalog.search("renal")
        self.assertTrue(renal)
        self.assertEqual(renal[0].path[-1], "Renal")
        self.assertNotEqual(renal[0].group, "All tags")

        pathology = catalog.search("renal pathology")
        self.assertTrue(pathology)
        self.assertEqual(pathology[0].path[-1], "Pathology")

        high_yield = catalog.search("high yield")
        self.assertEqual(high_yield[0].path, ("Yield", "High Yield"))

        utility = catalog.search("delete duplicate")
        self.assertTrue(utility)
        self.assertTrue(utility[0].hidden)
        nested_utility = next(
            facet
            for facet in catalog.anking
            if "$AnkiHub" in facet.value
        )
        self.assertTrue(nested_utility.hidden)

        self.assertEqual(
            catalog.find("topic", "#AK_Step1_v12::#Pathoma").group,
            "Resources",
        )

    def test_alias_typo_and_detected_browse_hierarchy(self) -> None:
        catalog = build_catalog(
            deck_names=("AnKing",),
            tags=(
                "#AK_Step1_v12::#FirstAid::14_Renal::Acute_Kidney_Injury",
                "#AK_Step1_v12::#B&B::Renal",
                "#AK_Step1_v12::^Systems::Renal",
            ),
        )
        self.assertTrue(catalog.search("FA renal"))
        self.assertTrue(catalog.search("bnb renal"))
        self.assertTrue(catalog.search("renla"))
        self.assertIn("Resources", catalog.browse_groups)
        roots = catalog.browse_children("Resources")
        first_aid = next(facet for facet in roots if facet.label == "First Aid")
        self.assertTrue(catalog.has_browse_children(first_aid))

    def test_equivalent_step_paths_collapse_without_losing_exact_selectors(self) -> None:
        step_1 = "#AK_Step1_v12::#FirstAid::07_Cardiovascular"
        step_2 = "#AK_Step2_v12::#FirstAid::07_Cardiovascular"
        catalog = build_catalog(deck_names=(), tags=(step_1, step_2))

        matches = tuple(
            facet
            for facet in catalog.search("cardiovascular", limit=20)
            if facet.group == "Resources"
            and facet.path == ("First Aid", "Cardiovascular")
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].values, (step_1, step_2))
        self.assertEqual(matches[0].scope_badges, ("Step 1", "Step 2"))

        definition = BuilderDefinition(
            filter_groups=(
                BuilderFilterGroup(
                    "cardiovascular",
                    FilterOperator.ANY,
                    tuple(BuilderSelector("tag", value) for value in matches[0].values),
                ),
            ),
            state_preset=StatePreset.ALL,
        )
        query = compile_builder_query(definition)
        self.assertIn(f'tag:"{step_1}" or tag:"{step_2}"', query)

    def test_different_anking_versions_are_not_collapsed(self) -> None:
        catalog = build_catalog(
            deck_names=(),
            tags=(
                "#AK_Step1_v11::#FirstAid::07_Cardiovascular",
                "#AK_Step2_v12::#FirstAid::07_Cardiovascular",
            ),
        )
        matches = tuple(
            facet
            for facet in catalog.search("cardiovascular", limit=20)
            if facet.group == "Resources"
            and facet.path == ("First Aid", "Cardiovascular")
        )
        self.assertEqual(len(matches), 2)

    def test_exact_match_does_not_hide_useful_prefix_matches(self) -> None:
        catalog = build_catalog(
            deck_names=(),
            tags=(
                "#AK_Step1_v12::#FirstAid::07_Cardiovascular",
                "#AK_Step1_v12::#Pixorize::03_Pharmacology::06_Cardiovascular_Pharm",
            ),
        )
        paths = {facet.path for facet in catalog.search("cardiovascular", limit=20)}
        self.assertIn(("First Aid", "Cardiovascular"), paths)
        self.assertIn(("Pixorize", "Pharmacology", "Cardiovascular Pharm"), paths)

    def test_builder_paths_ignore_context_display_depth_limit(self) -> None:
        from vellum.core.config import TopicParsingConfig

        catalog = build_catalog(
            deck_names=(),
            tags=("Medicine::One::Two::Three::Four",),
            topic_config=TopicParsingConfig(maximum_depth=2),
        )
        deepest = next(
            facet
            for facet in catalog.topics
            if facet.value == "Medicine::One::Two::Three::Four"
        )
        self.assertEqual(deepest.path, ("Medicine", "One", "Two", "Three", "Four"))


class StudyBuilderToolbarTests(unittest.TestCase):
    def test_builder_link_is_inserted_immediately_before_sync(self) -> None:
        class Toolbar:
            def __init__(self) -> None:
                self.created: tuple[object, ...] = ()

            def create_link(self, *args: object, **kwargs: object) -> str:
                self.created = (*args, kwargs)
                return "builder-link"

        module = object.__new__(StudyBuilderModule)
        module.open = lambda: None  # type: ignore[method-assign]
        toolbar = Toolbar()
        links = ["decks", "add", "browse", "stats", "sync"]

        module._toolbar_links(links, toolbar)

        self.assertEqual(links[-2:], ["builder-link", "sync"])
        self.assertEqual(toolbar.created[0], "vellum-study-builder")
        self.assertEqual(toolbar.created[1], "Builder")
        self.assertEqual(toolbar.created[-1]["id"], "vellum-study-builder")


class StudyRecipeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "vellum.sqlite3")
        self.database.migrate()
        self.repository = StudyRecipeRepository(self.database)

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_recipes_are_collection_scoped_and_dynamic(self) -> None:
        definition = BuilderDefinition(tags=("Renal",), limit=50)
        saved = self.repository.save("collection-a", "Renal focus", definition, now=100)
        self.assertEqual(self.repository.list("collection-a"), (saved,))
        self.assertEqual(self.repository.list("collection-b"), ())
        updated = self.repository.save(
            "collection-a",
            "Renal focus",
            BuilderDefinition(tags=("Renal",), limit=75),
            recipe_id=saved.recipe_id,
            now=200,
        )
        self.assertEqual(updated.created_at, 100)
        self.assertEqual(updated.definition.limit, 75)
        self.assertTrue(self.repository.mark_run("collection-a", saved.recipe_id, now=250))
        self.assertEqual(self.repository.get("collection-a", saved.recipe_id).last_run_at, 250)
        with self.assertRaises(ValueError):
            self.repository.save(
                "collection-b",
                "Must not move",
                definition,
                recipe_id=saved.recipe_id,
                now=300,
            )
        self.assertIsNone(self.repository.get("collection-b", saved.recipe_id))

    def test_recent_runs_do_not_store_snippets(self) -> None:
        definition = BuilderDefinition(text_query="renal", limit=10)
        recent = self.repository.add_recent(
            "collection-a",
            definition,
            metadata={"selected_count": 10},
            now=100,
        )
        self.assertEqual(recent.definition, definition)
        loaded = self.repository.recent("collection-a")
        self.assertEqual(loaded[0].metadata, {"selected_count": 10})
        with self.database.locked() as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(study_builder_recent)")
            }
            payload = str(
                connection.execute(
                    "SELECT definition_json FROM study_builder_recent LIMIT 1"
                ).fetchone()[0]
            )
        self.assertNotIn("snippet", columns)
        self.assertNotIn("snippet", payload)
        self.assertNotIn("total_count", payload)
        self.assertNotIn("ready_count", payload)
        self.assertNotIn("field_text", payload)


if __name__ == "__main__":
    unittest.main()
