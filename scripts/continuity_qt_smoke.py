#!/usr/bin/env python3
"""Render new native continuity dialogs without opening an Anki profile."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_vellum_namespace() -> None:
    package = types.ModuleType("vellum")
    package.__path__ = [str(ROOT)]
    package.__package__ = "vellum"
    sys.modules["vellum"] = package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--dark", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from aqt.qt import (
        QApplication,
        QCheckBox,
        QColor,
        QComboBox,
        QDialog,
        QLineEdit,
        QListWidget,
        QPalette,
        QPushButton,
        QToolButton,
        QTreeWidget,
        Qt,
    )
    from PyQt6.QtTest import QTest

    app = QApplication.instance() or QApplication([])
    if args.dark:
        palette = QPalette()
        for role, color in (
            (QPalette.ColorRole.Window, "#202124"),
            (QPalette.ColorRole.WindowText, "#f1f3f4"),
            (QPalette.ColorRole.Base, "#17181a"),
            (QPalette.ColorRole.AlternateBase, "#282a2d"),
            (QPalette.ColorRole.Text, "#f1f3f4"),
            (QPalette.ColorRole.PlaceholderText, "#9aa0a6"),
            (QPalette.ColorRole.Button, "#2d2f33"),
            (QPalette.ColorRole.ButtonText, "#f1f3f4"),
            (QPalette.ColorRole.Highlight, "#7aa2f7"),
            (QPalette.ColorRole.HighlightedText, "#111318"),
        ):
            palette.setColor(role, QColor(color))
        app.setPalette(palette)
    load_vellum_namespace()

    from vellum.continuity.return_ramp import RampSuggestion, ReturnRampWorkload
    from vellum.core.config import VellumConfig
    from vellum.core.db import Database
    from vellum.core.events import EventBus
    from vellum.builder.catalog import build_catalog
    from vellum.builder.models import (
        BuilderDefinition,
        BuilderPreview,
        BuilderWorkflow,
        PreviewCard,
        RecentBuilderRun,
        StudyRecipe,
    )
    from vellum.builder.scope import (
        DeckScopeNode,
        DeckTagScope,
        ScopedTagNode,
        TopicDeckScope,
    )
    from vellum.notes.repository import MindNoteRepository
    from vellum.sessions.debrief import (
        DebriefMindNote,
        DebriefTopic,
        SessionDebrief,
    )
    from vellum.ui.debrief import show_debrief, show_debrief_history
    from vellum.ui.help import show_help
    from vellum.ui.mind_notes import show_mind_note_editor, show_mind_note_history
    from vellum.ui.onboarding import show_onboarding
    from vellum.ui.return_ramp import show_return_ramp_dialog
    from vellum.ui.settings import show_settings
    from vellum.ui.study_builder import show_study_builder

    screenshots: list[str] = []
    original_exec = QDialog.exec

    def capture(filename: str, invoke: object, *, advance: int = 0) -> None:
        path = output / filename

        def intercepted(dialog: QDialog) -> int:
            dialog.show()
            for _index in range(10):
                app.processEvents()
            for _step in range(advance):
                button = next(
                    (
                        item
                        for item in dialog.findChildren(QPushButton)
                        if item.text() == "Continue"
                    ),
                    None,
                )
                if button is None:
                    raise RuntimeError("onboarding Continue button unavailable")
                button.click()
                for _index in range(5):
                    app.processEvents()
            if not dialog.grab().save(str(path)):
                raise RuntimeError(f"could not save {filename}")
            dialog.reject()
            return 0

        QDialog.exec = intercepted  # type: ignore[method-assign]
        try:
            invoke()  # type: ignore[operator]
        finally:
            QDialog.exec = original_exec  # type: ignore[method-assign]
        screenshots.append(filename)

    def capture_nonmodal(filename: str, invoke: object) -> None:
        path = output / filename
        dialog = invoke()  # type: ignore[operator]
        QTest.qWait(400)
        app.processEvents()
        if not dialog.grab().save(str(path)):
            raise RuntimeError(f"could not save {filename}")
        dialog.close()
        screenshots.append(filename)

    capture(
        "return-ramp.png",
        lambda: show_return_ramp_dialog(
            None,
            ReturnRampWorkload(
                absence_seconds=17 * 86400,
                available_cards=1_408,
                active_decks=6,
                new_cards=120,
                learning_cards=88,
                review_cards=1_200,
                estimated_minutes=172,
                suggestions=(
                    RampSuggestion(10, 48),
                    RampSuggestion(20, 96),
                    RampSuggestion(30, 143),
                ),
            ),
            resume_label=None,
            generated_session_waiting=False,
            can_start_time_machine=True,
            on_resume=lambda: None,
            on_start=lambda _minutes: None,
        ),
    )
    capture(
        "mind-note-editor.png",
        lambda: show_mind_note_editor(
            None,
            topic_label="Porphyria",
            topic_path=("Hematology", "Heme synthesis", "Porphyria"),
            on_save=lambda _body: None,
        ),
    )
    class FakeModules:
        @staticmethod
        def get(_name: str) -> object | None:
            return None

    class FakeApp:
        def __init__(self) -> None:
            self.config = VellumConfig()
            self.services = SimpleNamespace(
                persistence_available=True,
                events=EventBus(),
                modules=FakeModules(),
            )

        def apply_config(self, config: VellumConfig) -> None:
            self.config = config

    fake_app = FakeApp()
    builder_definition = BuilderDefinition(
        workflow=BuilderWorkflow.FIND_TOPICS,
        topic_tags=("#AK_Step1_v12::#FirstAid::14_Renal",),
        source_decks=("AnKing",),
        limit=100,
    )
    builder_catalog = build_catalog(
        deck_names=("AnKing", "Medicine::Renal"),
        tags=(
            "#AK_Step1_v12::#FirstAid::14_Renal::Pathology::ADTKD",
            "#AK_Step1_v12::#Pathoma::11_Kidney::Acute_Kidney_Injury",
            "#AK_Step1_v12::^Systems::Renal",
            "#AK_Step1_v12::#Low/HighYield::1-HighYield",
            "Medicine::Renal::Tubulointerstitial::ADTKD",
        ),
        note_types=("AnKingOverhaul", "Cloze"),
        card_types=("Card 1", "Cloze"),
    )
    builder_preview = BuilderPreview(
        generation=1,
        compiled_query='tag:"#AK_Step1_v12::#FirstAid::14_Renal" (is:due or is:new)',
        total_count=284,
        ready_count=176,
        suspended_count=92,
        buried_count=9,
        filtered_count=7,
        selected_card_ids=(101, 102, 103),
        selected_suspended_ids=(),
        cards=(
            PreviewCard(101, 201, "Autosomal dominant tubulointerstitial kidney disease…", "AnKing", "AnKingOverhaul", "Card 1", "Review", ("Renal", "High Yield")),
            PreviewCard(102, 202, "Renal papillary necrosis is associated with…", "AnKing", "AnKingOverhaul", "Card 1", "New", ("Renal", "First Aid")),
            PreviewCard(103, 203, "A patient with type IV RTA develops…", "Medicine › Renal", "Cloze", "Cloze", "Review", ("Renal",)),
        ),
    )

    def builder_window(*, view: str = "welcome") -> object:
        previewed: list[BuilderDefinition] = []

        def preview(definition: BuilderDefinition, generation: int, success: object, _failure: object) -> None:
            previewed.append(definition)
            success(
                BuilderPreview(
                    **{
                        **builder_preview.__dict__,
                        "generation": generation,
                    }
                )
            )

        def topic_decks(
            topics: tuple[str, ...],
            generation: int,
            include_empty: bool,
            success: object,
            _failure: object,
        ) -> None:
            nodes = (
                DeckScopeNode("AnKing", "AnKing", ("AnKing",), 284),
                DeckScopeNode(
                    "Medicine::Renal", "Renal", ("Medicine", "Renal"), 42
                ),
            )
            if include_empty:
                nodes = (*nodes, DeckScopeNode("Empty", "Empty", ("Empty",), 0))
            success(TopicDeckScope(generation, topics, nodes, 326))

        def deck_tags(
            decks: tuple[str, ...],
            generation: int,
            success: object,
            _failure: object,
        ) -> None:
            success(
                DeckTagScope(
                    generation,
                    decks,
                    (
                        ScopedTagNode(
                            ("#AK_Step1_v12::#FirstAid::14_Renal",),
                            "Renal",
                            ("First Aid", "Renal"),
                            "Resources",
                            284,
                            False,
                            ("Step 1",),
                        ),
                        ScopedTagNode(
                            ("#AK_Step1_v12::#Pathoma::11_Kidney",),
                            "Kidney",
                            ("Pathoma", "Kidney"),
                            "Resources",
                            118,
                        ),
                        ScopedTagNode(
                            ("#AK_Step1_v12::^Systems::Renal",),
                            "Renal",
                            ("Systems", "Renal"),
                            "Systems",
                            301,
                        ),
                    ),
                    326,
                )
            )

        window = show_study_builder(
            None,
            catalog=builder_catalog,
            recipes=(StudyRecipe("recipe", "collection", "Renal First Aid", builder_definition, 1, 1),),
            recent_runs=(RecentBuilderRun("run", "collection", builder_definition, None, 1),),
            config=replace(VellumConfig().study_builder, tutorial_version=1),
            on_topic_decks=topic_decks,
            on_deck_tags=deck_tags,
            on_preview=preview,
            on_build=lambda _request: None,
            on_save_recipe=lambda _name, definition, _recipe_id: StudyRecipe("saved", "collection", "Saved", definition, 1, 1),
            on_delete_recipe=lambda _recipe_id: True,
            on_open_browser=lambda _definition: None,
            on_tutorial_complete=lambda: None,
            on_closed=lambda: None,
        )
        app.processEvents()
        help_buttons = tuple(
            item
            for item in window.findChildren(QToolButton)
            if item.accessibleName().startswith(("Explain", "How Study Builder"))
        )
        if len(help_buttons) < 3 or any(not item.toolTip() for item in help_buttons):
            raise RuntimeError("Study Builder contextual help is missing or unlabeled")
        if view == "welcome":
            return window
        mode_name = (
            "Find Topics workflow"
            if view.startswith("find")
            else "Browse Collection workflow"
        )
        mode = next(
            button
            for button in window.findChildren(QPushButton)
            if button.accessibleName() == mode_name
        )
        mode.click()
        app.processEvents()
        if view.startswith("find"):
            finder = next(
                item
                for item in window.findChildren(QLineEdit)
                if item.accessibleName() == "Find topics and tags"
            )
            results = next(
                item
                for item in window.findChildren(QListWidget)
                if item.accessibleName() == "Matching topics and tag paths"
            )
            finder.setText("renal")
            app.processEvents()
            for required in ("First Aid", "Systems"):
                item = next(
                    results.item(index)
                    for index in range(results.count())
                    if required.casefold() in results.item(index).text().casefold()
                )
                results.itemClicked.emit(item)
            QTest.qWait(250)
            app.processEvents()
            if view == "find-topics":
                return window
            next_button = next(
                button
                for button in window.findChildren(QPushButton)
                if button.text().startswith("Continue to source decks")
            )
            next_button.click()
            app.processEvents()
            deck_tree = next(
                tree
                for tree in window.findChildren(QTreeWidget)
                if tree.accessibleName() == "Decks containing selected topics"
            )
            if deck_tree.topLevelItemCount() < 1:
                raise RuntimeError("Find Topics did not show relevant source decks")
            anking = deck_tree.topLevelItem(0)
            anking.setCheckState(0, Qt.CheckState.Checked)
            QTest.qWait(300)
            app.processEvents()
            if not previewed:
                raise RuntimeError("Find Topics did not preview a complete scope")
            definition = previewed[-1]
            if len(definition.topic_tags) != 2 or definition.source_decks != ("AnKing",):
                raise RuntimeError("Guided topic/deck semantics were not preserved")
            if view == "find-decks":
                return window
            inspect_button = next(
                button
                for button in window.findChildren(QPushButton)
                if button.accessibleName() == "Inspect Find Topics cards"
            )
            inspect_button.click()
            app.processEvents()
        else:
            deck_tree = next(
                tree
                for tree in window.findChildren(QTreeWidget)
                if tree.accessibleName() == "Source deck tree"
            )
            anking = deck_tree.topLevelItem(0)
            anking.setCheckState(0, Qt.CheckState.Checked)
            QTest.qWait(250)
            app.processEvents()
            if view == "browse-decks":
                return window
            next_button = next(
                button
                for button in window.findChildren(QPushButton)
                if button.text().startswith("Continue to tags")
            )
            next_button.click()
            app.processEvents()
            tag_tree = next(
                tree
                for tree in window.findChildren(QTreeWidget)
                if tree.accessibleName() == "Tags found in selected decks"
            )
            if tag_tree.topLevelItemCount() < 1:
                raise RuntimeError("Browse Collection did not receive scoped tags")
            section = tag_tree.topLevelItem(0)
            leaf = section.child(0).child(0)
            leaf.setCheckState(0, Qt.CheckState.Checked)
            QTest.qWait(300)
            app.processEvents()
            if not previewed or previewed[-1].workflow is not BuilderWorkflow.BROWSE_COLLECTION:
                raise RuntimeError("Browse Collection did not preview its tag scope")
            if view == "browse-tags":
                return window
            inspect_button = next(
                button
                for button in window.findChildren(QPushButton)
                if button.accessibleName() == "Inspect Browse Collection cards"
            )
            inspect_button.click()
            app.processEvents()
        return window

    capture_nonmodal("study-builder-welcome.png", builder_window)
    capture_nonmodal("study-builder-find-topics.png", lambda: builder_window(view="find-topics"))
    capture_nonmodal("study-builder-find-decks.png", lambda: builder_window(view="find-decks"))
    capture_nonmodal("study-builder-find-preview.png", lambda: builder_window(view="find-preview"))
    capture_nonmodal("study-builder-browse-decks.png", lambda: builder_window(view="browse-decks"))
    capture_nonmodal("study-builder-browse-tags.png", lambda: builder_window(view="browse-tags"))
    capture_nonmodal("study-builder-browse-preview.png", lambda: builder_window(view="browse-preview"))

    def narrow_builder_window() -> object:
        window = builder_window(view="find-topics")
        window.showNormal()
        window.resize(window.minimumWidth(), window.minimumHeight())
        return window

    capture_nonmodal("study-builder-narrow.png", narrow_builder_window)

    original_font = app.font()
    large_font = app.font()
    if large_font.pointSize() > 0:
        large_font.setPointSize(large_font.pointSize() + 3)
    else:
        large_font.setPixelSize(max(large_font.pixelSize() + 5, 18))
    app.setFont(large_font)
    try:
        capture_nonmodal(
            "study-builder-large-text.png",
            lambda: builder_window(view="browse-tags"),
        )
    finally:
        app.setFont(original_font)

    def open_builder_tutorial() -> None:
        window = builder_window()
        tutorial = next(
            item
            for item in window.findChildren(QToolButton)
            if item.accessibleName() == "How Study Builder works"
        )
        tutorial.click()
        window.close()

    capture("study-builder-tutorial.png", open_builder_tutorial)
    capture(
        "settings-memory.png",
        lambda: show_settings(None, fake_app, initial_tab="Memory"),
    )
    capture(
        "settings-return-ramp.png",
        lambda: show_settings(None, fake_app, initial_tab="Resume + Home"),
    )
    capture(
        "onboarding-welcome.png",
        lambda: show_onboarding(None, FakeApp(), ("#FirstAid", "Medicine")),
    )
    capture(
        "onboarding-setup.png",
        lambda: show_onboarding(None, FakeApp(), ("#FirstAid", "Medicine")),
        advance=1,
    )
    capture(
        "onboarding-topics.png",
        lambda: show_onboarding(None, FakeApp(), ("#FirstAid", "Medicine")),
        advance=2,
    )
    capture(
        "onboarding-commands.png",
        lambda: show_onboarding(None, FakeApp(), ("#FirstAid", "Medicine")),
        advance=3,
    )
    capture(
        "onboarding-ready.png",
        lambda: show_onboarding(None, FakeApp(), ("#FirstAid", "Medicine")),
        advance=4,
    )
    capture(
        "commands-help.png",
        lambda: show_help(None, FakeApp(), initial_section="Commands"),
    )
    debrief = SessionDebrief(
        session_id="visual-debrief",
        origin="time_machine",
        status="completed",
        started_at=1_780_000_000,
        ended_at=1_780_001_260,
        unique_card_count=42,
        answer_count=46,
        active_duration_ms=1_260_000,
        elapsed_seconds=1_300,
        planned_card_count=42,
        remaining_card_count=0,
        target_seconds=1_800,
        estimated_seconds=1_400,
        again_count=6,
        hard_count=4,
        good_count=31,
        easy_count=5,
        pace_delta_percent=-10,
        topics=(
            DebriefTopic(
                "renal-tubular",
                "Renal Tubular Disorders",
                ("Renal", "Renal Tubular Disorders"),
                "#FirstAid::Renal::Renal_Tubular_Disorders",
                12,
                14,
                3,
                2,
                1_780_001_200,
                True,
            ),
            DebriefTopic(
                "acid-base",
                "Acid–Base Physiology",
                ("Renal", "Acid–Base Physiology"),
                "#FirstAid::Renal::Acid_Base",
                9,
                10,
                1,
                1,
                1_780_001_100,
                False,
            ),
        ),
        mind_notes=(
            DebriefMindNote(1, "created", "Rebuild the RTA comparison.", "Renal Tubular Disorders"),
            DebriefMindNote(2, "resurfaced", "Explain the anion gap aloud.", "Acid–Base Physiology"),
        ),
        suggestion={
            "kind": "recovery",
            "title": "Recover Renal Tubular Disorders",
            "detail": "Again and Hard answers clustered here.",
        },
        handoff_text="Start by comparing distal and proximal RTA mechanisms.",
        handoff_acknowledged_at=None,
        completion_card_state="pending",
        created_at=1_780_001_260,
    )
    capture(
        "session-debrief-handoff.png",
        lambda: show_debrief(
            None,
            debrief,
            history=None,
            handoff_enabled=True,
            on_save_handoff=lambda _text: None,
            on_suggestion=lambda: None,
        ),
    )
    capture(
        "combined-session-history.png",
        lambda: show_debrief_history(
            None,
            (debrief,),
            (),
            (),
            open_debrief=lambda _session_id: None,
        ),
    )
    with tempfile.TemporaryDirectory(prefix="vellum-continuity-qt-") as directory:
        database = Database(Path(directory) / "vellum.sqlite3")
        database.migrate()
        repository = MindNoteRepository(database)
        repository.create(
            topic_id="porphyria",
            topic_label="Porphyria",
            topic_path=("Hematology", "Heme synthesis", "Porphyria"),
            body="I still don't fully understand why rifampin worsens porphyria.",
            source_card_id=None,
            created_at=1_780_000_000,
        )
        capture(
            "mind-notes-history.png",
            lambda: show_mind_note_history(None, repository),
        )
        database.close()

    print(
        json.dumps(
            {
                "config_absence_range": "any positive whole-day integer",
                "screenshots": screenshots,
                "scope": "native Qt dialogs without an Anki profile",
                "theme": "dark" if args.dark else "light",
                "defaults": {
                    "absence_days": VellumConfig().return_ramp.absence_days,
                    "backtrack": VellumConfig().backtrack.shortcut,
                    "mind_notes": VellumConfig().mind_notes.shortcut,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
