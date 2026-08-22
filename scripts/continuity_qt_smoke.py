#!/usr/bin/env python3
"""Render new native continuity dialogs without opening an Anki profile."""

from __future__ import annotations

import argparse
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

    from aqt.qt import QApplication, QColor, QDialog, QPalette, QPushButton

    app = QApplication.instance() or QApplication([])
    if args.dark:
        palette = QPalette()
        for role, color in (
            (QPalette.ColorRole.Window, "#202124"),
            (QPalette.ColorRole.WindowText, "#f1f3f4"),
            (QPalette.ColorRole.Base, "#17181a"),
            (QPalette.ColorRole.AlternateBase, "#282a2d"),
            (QPalette.ColorRole.Text, "#f1f3f4"),
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
