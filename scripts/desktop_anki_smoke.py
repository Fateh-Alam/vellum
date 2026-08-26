#!/usr/bin/env python3
"""Launch real Anki Qt against a disposable base and verify Vellum startup.

The caller must prepare ``BASE/addons21/vellum`` from the candidate archive.
Run from outside the repository so the source ``anki/`` adapter cannot shadow
Anki's installed package. This script never searches for a user profile.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--screenshot-dir", type=Path)
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--module-matrix", action="store_true")
    args = parser.parse_args()
    base = args.base.resolve()
    expected_addon = base / "addons21" / "vellum" / "manifest.json"
    if not expected_addon.is_file():
        raise SystemExit(f"prepared Vellum add-on missing: {expected_addon}")

    # Prevent Vellum's first-launch onboarding modal from blocking this
    # unattended harness before its explicit dialog-capture phase. This only
    # writes inside the disposable add-on copy prepared by the caller.
    addon_dir = expected_addon.parent
    config = json.loads((addon_dir / "config.json").read_text(encoding="utf-8"))
    config["onboarding_completed"] = True
    config["onboarding_version"] = 2
    config["onboarding_invitation_version"] = 2
    (addon_dir / "meta.json").write_text(
        json.dumps({"config": config}),
        encoding="utf-8",
    )

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    os.environ.setdefault("ANKI_NOHIGHDPI", "1")

    import aqt
    import anki.lang
    from aqt.profiles import ProfileManager

    # Seed a real but disposable profile so Anki never opens its first-run
    # language/profile modals in the unattended offscreen harness.
    profile_name = "VellumQA"
    base_folder = ProfileManager.get_created_base_folder(str(base))
    profile_manager = ProfileManager(base_folder)
    profile_manager.setupMeta()
    profile_manager.meta["firstRun"] = False
    if args.dark:
        profile_manager.meta["theme"] = 2
    profile_manager.setLang(anki.lang.get_def_lang("en")[1])
    profile_manager.create(profile_name)
    profile_manager.load(profile_name)
    profile_manager.profile["autoSync"] = False
    profile_manager.save()
    profile_manager.db.close()

    # Anki uses a per-user local socket even when --base differs. Give this
    # isolated test its own socket so a running personal Anki is never reused.
    aqt.AnkiApp.KEY = f"anki-vellum-desktop-smoke-{os.getpid()}"
    app = aqt._run(
        argv=[
            "Anki",
            "-b",
            str(base),
            "-p",
            profile_name,
            "-l",
            "en",
        ],
        exec=False,
    )
    if app is None:
        raise RuntimeError("Anki Qt did not create an isolated application")

    deadline = time.monotonic() + args.timeout
    loaded = None
    while time.monotonic() < deadline:
        app.processEvents()
        mw = aqt.mw
        module = sys.modules.get("vellum")
        addon_app = getattr(module, "APP", None) if module is not None else None
        if mw is not None and mw.col is not None and addon_app is not None:
            loaded = (mw, addon_app)
            break
        time.sleep(0.02)

    if loaded is None:
        raise RuntimeError("Vellum did not finish loading in disposable Anki")

    mw, addon_app = loaded
    if "vellum-study-builder" not in mw.toolbar.link_handlers:
        raise RuntimeError("Study Builder top-toolbar link was not installed")
    running = sorted(addon_app.services.modules.running_names())
    expected_running = sorted(
        [
            "backtrack",
            "context",
            "home_panel",
            "hud",
            "mind_notes",
            "recovery",
            "resume",
            "return_ramp",
            "session_debrief",
            "study_builder",
            "time_machine",
        ]
    )
    if running != expected_running:
        raise RuntimeError(
            f"unexpected active module set: {running}; expected {expected_running}"
        )

    module_matrix: dict[str, list[str]] = {}
    if args.module_matrix:
        from vellum.core.config import ModuleFlags

        module_names = tuple(ModuleFlags.__dataclass_fields__)

        def flags(*enabled_names: str) -> ModuleFlags:
            enabled = set(enabled_names)
            return ModuleFlags(
                **{name: name in enabled for name in module_names}
            )

        cases = {
            "context_only": flags("context"),
            "recovery_only": flags("recovery"),
            "time_machine_only": flags("time_machine"),
            "resume_only": flags("resume"),
            "return_ramp_only": flags("return_ramp"),
            "backtrack_only": flags("backtrack"),
            "mind_notes_only": flags("mind_notes"),
            "hud_only": flags("hud"),
            "context_recovery": flags("context", "recovery"),
            "time_machine_resume": flags("time_machine", "resume"),
            "study_builder_only": flags("study_builder"),
            "all_modules": flags(*module_names),
            "all_disabled": flags(),
        }
        original_config = addon_app.config
        for label, case_flags in cases.items():
            addon_app.apply_config(replace(original_config, modules=case_flags))
            for _index in range(10):
                app.processEvents()
            actual = sorted(addon_app.services.modules.running_names())
            expected = sorted(
                name for name in module_names if case_flags.enabled(name)
            )
            if actual != expected:
                raise RuntimeError(
                    f"module matrix {label} mismatch: {actual}; expected {expected}"
                )
            module_matrix[label] = actual

        addon_app.apply_config(replace(original_config, enabled=False))
        for _index in range(10):
            app.processEvents()
        master_disabled = sorted(addon_app.services.modules.running_names())
        if master_disabled:
            raise RuntimeError(
                f"master-disabled Vellum still has running modules: {master_disabled}"
            )
        module_matrix["master_disabled"] = master_disabled
        addon_app.apply_config(original_config)
        for _index in range(10):
            app.processEvents()

    screenshots: list[str] = []
    reviewer_next_card_ms: float | None = None
    generated_cleanup: dict[str, object] = {}
    if args.screenshot_dir is not None:
        screenshot_dir = args.screenshot_dir.resolve()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        from aqt.qt import QDialog, QPushButton

        mw.resize(1180, 760)
        mw.moveToState("deckBrowser")
        mw.deckBrowser.refresh()
        for _index in range(120):
            app.processEvents()
            time.sleep(0.02)
        main_path = screenshot_dir / "deck-browser-home.png"
        if not mw.grab().save(str(main_path)):
            raise RuntimeError("unable to save deck browser screenshot")
        screenshots.append(main_path.name)

        mw.toolbar.link_handlers["vellum-study-builder"]()
        builder_module = addon_app.services.modules.get("study_builder")
        builder_deadline = time.monotonic() + 10
        builder_window = None
        while time.monotonic() < builder_deadline:
            app.processEvents()
            builder_window = getattr(builder_module, "_window", None)
            if builder_window is not None and builder_window.isVisible():
                break
            time.sleep(0.02)
        if builder_window is None or not builder_window.isVisible():
            raise RuntimeError("Study Builder toolbar link did not open its window")
        builder_path = screenshot_dir / "study-builder-toolbar.png"
        if not builder_window.grab().save(str(builder_path)):
            raise RuntimeError("unable to save toolbar-launched Study Builder")
        screenshots.append(builder_path.name)
        builder_window.close()
        for _index in range(10):
            app.processEvents()

        original_exec = QDialog.exec

        def capture_dialog(filename: str, invoke: object, *, advance: int = 0) -> None:
            path = screenshot_dir / filename

            def capture(dialog: QDialog) -> int:
                dialog.show()
                for _index in range(30):
                    app.processEvents()
                    time.sleep(0.01)
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
                    for _index in range(10):
                        app.processEvents()
                        time.sleep(0.005)
                if not dialog.grab().save(str(path)):
                    raise RuntimeError(f"unable to save dialog screenshot: {filename}")
                QDialog.reject(dialog)
                return 0

            QDialog.exec = capture  # type: ignore[method-assign]
            try:
                invoke()  # type: ignore[operator]
            finally:
                QDialog.exec = original_exec  # type: ignore[method-assign]
            screenshots.append(path.name)

        from vellum.anki.time_machine import TimeMachineDeckChoice
        from vellum.continuity.return_ramp import RampSuggestion, ReturnRampWorkload
        from vellum.sessions.generated_decks import GeneratedDeckCard
        from vellum.sessions.models import (
            Session,
            SessionOrigin,
            SessionStatus,
            SessionTopicContext,
        )
        from vellum.sessions.resume import ResumeAssessment, ResumeMode
        from vellum.timing.models import SessionEstimate, TimingBucket
        from vellum.ui.onboarding import show_onboarding
        from vellum.ui.mind_notes import show_mind_note_editor, show_mind_note_history
        from vellum.ui.return_ramp import show_return_ramp_dialog
        from vellum.ui.history import show_generated_deck_history
        from vellum.ui.recovery import show_recovery_dialog
        from vellum.ui.resume import show_resume_dialog
        from vellum.ui.settings import show_settings
        from vellum.ui.time_machine import (
            show_deck_selection_dialog,
            show_duration_dialog,
            show_estimate_dialog,
        )

        capture_dialog(
            "settings.png",
            lambda: show_settings(mw, addon_app),
        )
        original_config = addon_app.config
        addon_app.services.config_store.save(
            replace(original_config, onboarding_completed=False)
        )
        try:
            capture_dialog(
                "onboarding.png",
                lambda: show_onboarding(
                    mw, addon_app, ("#FirstAid", "Medicine")
                ),
            )
            capture_dialog(
                "onboarding-setup.png",
                lambda: show_onboarding(
                    mw, addon_app, ("#FirstAid", "Medicine")
                ),
                advance=1,
            )
        finally:
            addon_app.services.config_store.save(original_config)
        capture_dialog(
            "recovery.png",
            lambda: show_recovery_dialog(
                mw,
                ("Medicine", "Renal", "Tubulointerstitial Disorders"),
                default_level_index=2,
                config=addon_app.config.recovery,
            ),
        )
        capture_dialog(
            "time-machine.png",
            lambda: show_duration_dialog(
                mw,
                addon_app.config.time_machine.presets_minutes,
                lambda _minutes: None,
            ),
        )
        capture_dialog(
            "time-machine-decks.png",
            lambda: show_deck_selection_dialog(
                mw,
                20,
                (
                    TimeMachineDeckChoice(1, "AnKing", 303, 0, 12, 291),
                    TimeMachineDeckChoice(2, "Sketchy Micro", 161, 7, 0, 154),
                    TimeMachineDeckChoice(3, "Pathoma", 35, 35, 0, 0),
                    TimeMachineDeckChoice(4, "Empty Archive", 0, 0, 0, 0),
                ),
                lambda _deck_ids: None,
            ),
        )
        estimate = SessionEstimate(
            expected_cards=74,
            estimated_seconds=1_185,
            remaining_buffer_seconds=15,
            per_bucket={
                TimingBucket.NEW: 12,
                TimingBucket.LEARNING: 8,
                TimingBucket.REVIEW: 54,
            },
            fallback_buckets=(TimingBucket.NEW,),
        )
        capture_dialog(
            "time-machine-estimate.png",
            lambda: show_estimate_dialog(
                mw,
                20,
                estimate,
                126,
                lambda: None,
                scope_label="All decks",
                active_decks=4,
            ),
        )
        now = int(time.time())
        history_session = Session(
            id="visual-history",
            started_at=now - 1_200,
            last_active_at=now - 40,
            ended_at=now - 40,
            status=SessionStatus.COMPLETED,
            deck_id=88,
            deck_name="Vellum Study by Time - 20 min",
            query="all-decks",
            target_seconds=1_200,
            origin=SessionOrigin.TIME_MACHINE,
            reviewed_count=2,
            starting_due_count=3,
            estimated_total=3,
        )
        history_repository = addon_app.services.generated_decks
        history_repository.create(
            history_session,
            feature="time_machine",
            scope="all-decks",
            cards=(
                GeneratedDeckCard(10001, 20001, 1, "AnKing", 1, "review"),
                GeneratedDeckCard(10002, 20002, 2, "Pathoma", 2, "learning"),
                GeneratedDeckCard(10003, 20003, 3, "Sketchy Micro", 3, "new"),
            ),
            metadata={"duration_minutes": 20, "scope_label": "All decks"},
        )
        history_repository.record_answer(
            history_session.id,
            card_id=10001,
            answered_at=(now - 100) * 1000,
            rating=1,
            duration_ms=1800,
        )
        history_repository.record_answer(
            history_session.id,
            card_id=10001,
            answered_at=(now - 80) * 1000,
            rating=3,
            duration_ms=950,
        )
        history_repository.mark_status(history_session)
        history_repository.mark_removed(
            history_session.id, reason="exhausted", removed_at=now - 40
        )
        capture_dialog(
            "session-history.png",
            lambda: show_generated_deck_history(mw, history_repository),
        )
        resume_session = Session(
            id="visual-qa",
            started_at=now - 2_400,
            last_active_at=now - 1_800,
            status=SessionStatus.INTERRUPTED,
            deck_id=1,
            deck_name="Reproductive Pharmacology",
            origin=SessionOrigin.NORMAL,
            reviewed_count=126,
            starting_due_count=184,
            last_topic_id="visual-topic",
        )
        assessment = ResumeAssessment(
            session=resume_session,
            mode=ResumeMode.CONTEXT,
            age_seconds=1_800,
            stale=False,
            expected_remaining=58,
            current_due=74,
            newly_due=16,
            explanation=(
                "Anki's current due queue differs from the saved checkpoint."
            ),
        )
        capture_dialog(
            "resume.png",
            lambda: show_resume_dialog(
                mw, assessment, lambda: None, lambda: None
            ),
        )
        capture_dialog(
            "return-ramp.png",
            lambda: show_return_ramp_dialog(
                mw,
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
        capture_dialog(
            "mind-note-editor.png",
            lambda: show_mind_note_editor(
                mw,
                topic_label="Porphyria",
                topic_path=("Hematology", "Heme synthesis", "Porphyria"),
                on_save=lambda _body: None,
            ),
        )
        addon_app.services.mind_notes.create(
            topic_id="visual-porphyria",
            topic_label="Porphyria",
            topic_path=("Hematology", "Heme synthesis", "Porphyria"),
            body="I still don't fully understand why rifampin worsens porphyria.",
            source_card_id=None,
            created_at=now - 3 * 86400,
        )
        capture_dialog(
            "mind-notes-history.png",
            lambda: show_mind_note_history(mw, addon_app.services.mind_notes),
        )

        # Render a real Reviewer question/answer transition using one synthetic
        # card in this disposable collection. No user card or scheduling state
        # is reachable from the isolated base.
        qa_deck_id = mw.col.decks.id("Vellum Visual QA")
        for index in range(2):
            note = mw.col.new_note(mw.col.models.current())
            note["Front"] = (
                "Which nephron segment is affected in ADTKD?"
                if index == 0
                else "What is the dominant pathological compartment in ADTKD?"
            )
            note["Back"] = "The tubulointerstitial compartment and tubular function."
            note.tags = ["Medicine::Renal::Tubulointerstitial_Disorders::ADTKD"]
            mw.col.add_note(note, qa_deck_id)
        mw.col.decks.select(qa_deck_id)
        mw.moveToState("review")
        for _index in range(180):
            app.processEvents()
            if getattr(getattr(mw, "reviewer", None), "card", None) is not None:
                time.sleep(0.02)
            else:
                time.sleep(0.01)
        mw.reviewer.web.eval(
            "window.VellumContext&&window.VellumContext.toggle();"
        )
        for _index in range(100):
            app.processEvents()
            time.sleep(0.01)
        reviewer_question = screenshot_dir / "reviewer-context-question.png"
        if not mw.grab().save(str(reviewer_question)):
            raise RuntimeError("unable to save Reviewer question screenshot")
        screenshots.append(reviewer_question.name)
        mind_module = addon_app.services.modules.get("mind_notes")
        mind_context = getattr(mind_module, "_current_context", None)
        if mind_context is None or not mind_context.primary_topic_id:
            raise RuntimeError("Mind Notes did not resolve the reviewer topic")
        addon_app.services.mind_notes.create(
            topic_id=mind_context.primary_topic_id,
            topic_label=mind_context.topic_path[-1],
            topic_path=mind_context.topic_path,
            body="Rebuild the mechanism before accepting the memorized association.",
            source_card_id=mind_context.card_id,
            created_at=now - 3 * 86400,
        )
        mind_module._deliver(mind_context.card_id)
        for _index in range(80):
            app.processEvents()
            time.sleep(0.01)
        reviewer_mind_note = screenshot_dir / "reviewer-mind-note.png"
        if not mw.grab().save(str(reviewer_mind_note)):
            raise RuntimeError("unable to save Reviewer Mind Note screenshot")
        screenshots.append(reviewer_mind_note.name)
        mw.reviewer._showAnswer()
        for _index in range(100):
            app.processEvents()
            time.sleep(0.01)
        reviewer_answer = screenshot_dir / "reviewer-context-answer.png"
        if not mw.grab().save(str(reviewer_answer)):
            raise RuntimeError("unable to save Reviewer answer screenshot")
        screenshots.append(reviewer_answer.name)
        first_card_id = int(mw.reviewer.card.id)
        transition_started = time.perf_counter()
        mw.reviewer._answerCard(3)
        transition_deadline = time.monotonic() + 5
        while time.monotonic() < transition_deadline:
            app.processEvents()
            current_card = getattr(mw.reviewer, "card", None)
            if (
                current_card is not None
                and int(current_card.id) != first_card_id
                and mw.reviewer.state == "question"
            ):
                reviewer_next_card_ms = (
                    time.perf_counter() - transition_started
                ) * 1000
                break
            time.sleep(0.001)
        if reviewer_next_card_ms is None:
            raise RuntimeError("Reviewer did not reach the next card within 5 seconds")
        backtrack_module = addon_app.services.modules.get("backtrack")
        capture_dialog("backtrack.png", backtrack_module.open)
        mw.moveToState("deckBrowser")
        for _index in range(40):
            app.processEvents()
            time.sleep(0.01)

        # Exercise the real generated-session lifecycle rather than manually
        # deleting its deck: exact queue creation -> Reviewer answers -> native
        # reviewer end hook -> verified owned-deck removal -> durable history.
        from vellum.anki.time_machine import collect_selected_deck_queue

        generated_source_id = int(mw.col.decks.id("Vellum Generated QA"))
        generated_card_ids: list[int] = []
        for index in range(2):
            note = mw.col.new_note(mw.col.models.current())
            note["Front"] = f"Bounded generated session card {index + 1}"
            note["Back"] = "Disposable generated-session answer"
            note.tags = ["Medicine::Generated_QA"]
            mw.col.add_note(note, generated_source_id)
            card = note.cards()[0]
            card.type = 2
            card.queue = 2
            card.ivl = 10
            card.due = int(mw.col.sched.today) - 1
            mw.col.update_card(card)
            generated_card_ids.append(int(card.id))
        generated_snapshot = collect_selected_deck_queue(
            mw.col, (generated_source_id,), fetch_limit=20
        )
        if len(generated_snapshot.card_ids) != 2:
            raise RuntimeError("generated lifecycle fixture did not produce two cards")
        time_machine_module = addon_app.services.modules.get("time_machine")
        time_machine_module._start_session(
            1,
            generated_snapshot,
            2,
            14.0,
            scope_label="Vellum Generated QA",
            session_query=f"deck-ids:{generated_source_id}",
        )
        deadline = time.monotonic() + 8
        generated_session = None
        while time.monotonic() < deadline:
            app.processEvents()
            current = addon_app.services.sessions.current
            if (
                current is not None
                and current.origin is SessionOrigin.TIME_MACHINE
                and getattr(getattr(mw, "reviewer", None), "card", None) is not None
            ):
                generated_session = current
                break
            time.sleep(0.01)
        if generated_session is None:
            raise RuntimeError("generated Study by Time session did not reach Reviewer")
        generated_deck_id = int(generated_session.deck_id)
        generated_deck_name = str(generated_session.deck_name)
        for _index in range(2):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                app.processEvents()
                if (
                    getattr(getattr(mw, "reviewer", None), "card", None) is not None
                    and mw.reviewer.state == "question"
                ):
                    break
                time.sleep(0.005)
            else:
                raise RuntimeError("generated Reviewer card did not become ready")
            mw.reviewer._showAnswer()
            for _event in range(20):
                app.processEvents()
            mw.reviewer._answerCard(3)
            for _event in range(40):
                app.processEvents()
                time.sleep(0.005)

        deadline = time.monotonic() + 10
        saved_history = None
        saved_debrief = None
        while time.monotonic() < deadline:
            app.processEvents()
            saved_history = addon_app.services.generated_decks.get(
                generated_session.id
            )
            saved_debrief = addon_app.services.debriefs.get(generated_session.id)
            if (
                mw.col.decks.name_if_exists(generated_deck_id) is None
                and saved_history is not None
                and saved_history.status == "completed"
                and saved_history.removed_at is not None
                and saved_debrief is not None
                and saved_debrief.completion_card_state == "pending"
            ):
                break
            time.sleep(0.01)
        else:
            raise RuntimeError(
                "generated session did not auto-delete and complete history"
            )
        if saved_history is None or len(saved_history.cards) != 2:
            raise RuntimeError("generated history manifest is incomplete")
        if len(saved_history.answers) != 2:
            raise RuntimeError("generated history did not retain both answers")
        if any(
            int(mw.col.get_card(card_id).did) != generated_source_id
            for card_id in generated_card_ids
        ):
            raise RuntimeError("generated cards did not return to their home deck")
        if getattr(mw, "state", None) != "deckBrowser":
            mw.moveToState("deckBrowser")
        mw.deckBrowser.refresh()
        for _index in range(100):
            app.processEvents()
            time.sleep(0.01)
        completion_path = screenshot_dir / "deck-browser-debrief.png"
        if not mw.grab().save(str(completion_path)):
            raise RuntimeError("unable to save Session Debrief completion card")
        screenshots.append(completion_path.name)
        debrief_module = addon_app.services.modules.get("session_debrief")
        capture_dialog(
            "session-debrief.png",
            lambda: debrief_module.open(generated_session.id),
        )
        addon_app.services.debriefs.save_handoff(
            generated_session.id,
            "Compare the tubular mechanisms before the next renal session.",
        )
        debrief_module._render(None)
        for _index in range(80):
            app.processEvents()
            time.sleep(0.01)
        handoff_path = screenshot_dir / "deck-browser-handoff.png"
        if not mw.grab().save(str(handoff_path)):
            raise RuntimeError("unable to save Session Debrief handoff card")
        screenshots.append(handoff_path.name)
        from vellum.sessions.debrief import DebriefRepository

        reloaded_debriefs = DebriefRepository(addon_app.services.database)
        if reloaded_debriefs.get(generated_session.id).completion_card_state != "opened":
            raise RuntimeError("Debrief completion state did not survive repository reload")
        if reloaded_debriefs.active_handoff() is None:
            raise RuntimeError("Debrief handoff did not survive repository reload")
        normal_session = Session(
            id="visual-normal-debrief",
            started_at=now - 300,
            last_active_at=now - 250,
            ended_at=now - 250,
            status=SessionStatus.COMPLETED,
            origin=SessionOrigin.NORMAL,
            reviewed_count=1,
            starting_due_count=1,
            estimated_total=1,
            estimated_seconds=7.0,
        )
        addon_app.services.sessions.repository.save(normal_session)
        addon_app.services.sessions.repository.record_answer(
            normal_session,
            card_id=991001,
            reviewed_at=(now - 260) * 1000,
            rating=3,
            duration_ms=6_500,
            topic=SessionTopicContext(
                topic_id="visual-normal-topic",
                label="Normal Study",
                path=("Medicine", "Normal Study"),
                raw_topic_tag="Medicine::Normal_Study",
            ),
        )
        normal_debrief = addon_app.services.debriefs.finalize(
            normal_session,
            show_completion_card=False,
            recovery_enabled=True,
        )
        if normal_debrief is None or addon_app.services.debriefs.pending_completion() is not None:
            raise RuntimeError("ordinary session created an automatic completion card")
        capture_dialog("combined-session-history.png", debrief_module.open_history)

        # Exercise natural Recovery exhaustion through the same Reviewer hooks.
        from anki.decks import FilteredDeckConfig
        from vellum.anki.recovery import collect_recovery_candidates
        from vellum.recovery.models import RecoveryMode
        from vellum.recovery.planner import build_recovery_plan
        from vellum.sessions.generated_decks import collect_generated_deck_cards

        recovery_source_id = int(mw.col.decks.id("Vellum Recovery QA"))
        recovery_card_ids: list[int] = []
        for index in range(2):
            note = mw.col.new_note(mw.col.models.current())
            note["Front"] = f"Recovery lifecycle card {index + 1}"
            note["Back"] = "Disposable Recovery answer"
            note.tags = ["Medicine::Recovery_Generated_QA"]
            mw.col.add_note(note, recovery_source_id)
            card = note.cards()[0]
            card.type = 2
            card.queue = 2
            card.ivl = 10
            card.due = int(mw.col.sched.today) - 1
            mw.col.update_card(card)
            recovery_card_ids.append(int(card.id))
        candidates = collect_recovery_candidates(
            mw.col,
            "Medicine::Recovery_Generated_QA",
            current_card_id=recovery_card_ids[0],
            recent_failure_days=14,
        )
        recovery_plan = build_recovery_plan(
            topic_label="Recovery Generated QA",
            raw_tag_prefix="Medicine::Recovery_Generated_QA",
            mode=RecoveryMode.FULL,
            candidates=candidates.candidates,
            config=addon_app.config.recovery,
        )
        recovery_deck = mw.col.sched.get_or_create_filtered_deck(0)
        recovery_deck.name = "Vellum Recovery - Recovery Generated QA"
        recovery_deck.config.reschedule = True
        del recovery_deck.config.search_terms[:]
        recovery_deck.config.search_terms.append(
            FilteredDeckConfig.SearchTerm(
                search="cid:" + ",".join(str(card_id) for card_id in recovery_plan.card_ids),
                limit=len(recovery_plan.card_ids),
                order=6,
            )
        )
        recovery_operation = mw.col.sched.add_or_update_filtered_deck(recovery_deck)
        recovery_deck_id = int(recovery_operation.id)
        recovery_count = int(mw.col.sched.rebuild_filtered_deck(recovery_deck_id).count)
        if recovery_count != 2:
            raise RuntimeError("Recovery lifecycle fixture did not build two cards")
        recovery_cards = collect_generated_deck_cards(
            mw.col,
            recovery_deck_id,
            tuple(recovery_card_ids),
            buckets={card_id: "review" for card_id in recovery_card_ids},
        )
        recovery_module = addon_app.services.modules.get("recovery")
        recovery_module._select_start(
            recovery_deck_id,
            recovery_deck.name,
            recovery_plan,
            "recovery-generated-qa",
            recovery_cards,
        )
        deadline = time.monotonic() + 8
        recovery_session = None
        while time.monotonic() < deadline:
            app.processEvents()
            current = addon_app.services.sessions.current
            if (
                current is not None
                and current.origin is SessionOrigin.RECOVERY
                and getattr(getattr(mw, "reviewer", None), "card", None) is not None
            ):
                recovery_session = current
                break
            time.sleep(0.01)
        if recovery_session is None:
            raise RuntimeError("Recovery lifecycle did not reach Reviewer")
        for _index in range(2):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                app.processEvents()
                if (
                    getattr(getattr(mw, "reviewer", None), "card", None) is not None
                    and mw.reviewer.state == "question"
                ):
                    break
                time.sleep(0.005)
            else:
                raise RuntimeError("Recovery Reviewer card did not become ready")
            mw.reviewer._showAnswer()
            for _event in range(20):
                app.processEvents()
            mw.reviewer._answerCard(3)
            for _event in range(40):
                app.processEvents()
                time.sleep(0.005)
        deadline = time.monotonic() + 10
        recovery_history = None
        recovery_debrief = None
        while time.monotonic() < deadline:
            app.processEvents()
            recovery_history = addon_app.services.generated_decks.get(recovery_session.id)
            recovery_debrief = addon_app.services.debriefs.get(recovery_session.id)
            if (
                mw.col.decks.name_if_exists(recovery_deck_id) is None
                and recovery_history is not None
                and recovery_history.status == "completed"
                and recovery_history.removed_at is not None
                and recovery_debrief is not None
                and recovery_debrief.completion_card_state == "pending"
            ):
                break
            time.sleep(0.01)
        else:
            raise RuntimeError("Recovery exhaustion did not finalize after exact deck cleanup")
        if any(int(mw.col.get_card(card_id).did) != recovery_source_id for card_id in recovery_card_ids):
            raise RuntimeError("Recovery cards did not return to their home deck")
        addon_app.services.debriefs.set_completion_state(recovery_session.id, "dismissed")

        # Explicit Finish must report returned cards without creating a Resume candidate.
        finish_source_id = int(mw.col.decks.id("Vellum Explicit Finish QA"))
        finish_card_ids: list[int] = []
        for index in range(2):
            note = mw.col.new_note(mw.col.models.current())
            note["Front"] = f"Explicit Finish card {index + 1}"
            note["Back"] = "Disposable explicit-finish answer"
            note.tags = ["Medicine::Explicit_Finish_QA"]
            mw.col.add_note(note, finish_source_id)
            card = note.cards()[0]
            card.type = 2
            card.queue = 2
            card.ivl = 10
            card.due = int(mw.col.sched.today) - 1
            mw.col.update_card(card)
            finish_card_ids.append(int(card.id))
        finish_snapshot = collect_selected_deck_queue(
            mw.col, (finish_source_id,), fetch_limit=20
        )
        time_machine_module._start_session(
            1,
            finish_snapshot,
            2,
            14.0,
            scope_label="Vellum Explicit Finish QA",
            session_query=f"deck-ids:{finish_source_id}",
        )
        deadline = time.monotonic() + 8
        finish_session = None
        while time.monotonic() < deadline:
            app.processEvents()
            current = addon_app.services.sessions.current
            if (
                current is not None
                and current.origin is SessionOrigin.TIME_MACHINE
                and current.id != generated_session.id
                and getattr(getattr(mw, "reviewer", None), "card", None) is not None
            ):
                finish_session = current
                break
            time.sleep(0.01)
        if finish_session is None:
            raise RuntimeError("explicit Finish fixture did not reach Reviewer")
        mw.reviewer._showAnswer()
        for _event in range(20):
            app.processEvents()
        mw.reviewer._answerCard(3)
        for _event in range(40):
            app.processEvents()
            time.sleep(0.005)
        time_machine_module._remove_owned_deck(finish_session, abandon=True)
        deadline = time.monotonic() + 10
        finish_debrief = None
        finish_history = None
        while time.monotonic() < deadline:
            app.processEvents()
            finish_history = addon_app.services.generated_decks.get(finish_session.id)
            finish_debrief = addon_app.services.debriefs.get(finish_session.id)
            if (
                mw.col.decks.name_if_exists(int(finish_session.deck_id)) is None
                and finish_history is not None
                and finish_history.status == "abandoned"
                and finish_history.removed_at is not None
                and finish_debrief is not None
            ):
                break
            time.sleep(0.01)
        else:
            raise RuntimeError("explicit Finish did not finalize after exact deck cleanup")
        if finish_debrief.remaining_card_count != 1:
            raise RuntimeError("explicit Finish did not report one safely returned card")
        if finish_debrief.suggestion.get("kind") != "time_machine":
            raise RuntimeError("explicit Finish offered an invalid next action")
        if addon_app.services.sessions.repository.latest_generated_resumable() is not None:
            raise RuntimeError("explicitly finished cards were offered as resumable")
        if any(int(mw.col.get_card(card_id).did) != finish_source_id for card_id in finish_card_ids):
            raise RuntimeError("explicitly finished cards did not return home")
        addon_app.services.debriefs.set_completion_state(finish_session.id, "dismissed")
        generated_cleanup = {
            "bounded_cards": len(saved_history.cards),
            "answer_events": len(saved_history.answers),
            "deck_name": generated_deck_name,
            "deck_removed": True,
            "cards_returned_home": True,
            "history_status": saved_history.status,
            "removal_reason": saved_history.removal_reason,
            "debrief_after_cleanup": True,
            "completion_state_repository_reload": True,
            "handoff_repository_reload": True,
            "normal_session_quiet_history": True,
            "recovery_exhaustion_after_cleanup": True,
            "recovery_cards_returned_home": True,
            "explicit_finish_returned_cards": finish_debrief.remaining_card_count,
            "explicit_finish_not_resumable": True,
        }

    log_path = base / "addons21" / "vellum" / "user_files" / "vellum.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    error_lines = [line for line in log_text.splitlines() if " ERROR " in line]
    result = {
        "anki_version": importlib.metadata.version("anki"),
        "base": "disposable temporary Anki base",
        "collection_open": True,
        "error_log_lines": len(error_lines),
        "generated_session_cleanup": generated_cleanup,
        "menu_installed": addon_app.menu is not None,
        "module_matrix": module_matrix,
        "persistence_available": addon_app.services.persistence_available,
        "running_modules": running,
        "reviewer_next_card_ms": (
            round(reviewer_next_card_ms, 3)
            if reviewer_next_card_ms is not None
            else None
        ),
        "schema_version": addon_app.services.database.schema_version,
        "screenshots": screenshots,
        "study_builder_toolbar_link": True,
        "settings_action_installed": addon_app.settings_action is not None,
        "theme": "dark" if args.dark else "light",
        "vellum_loaded": True,
    }
    if error_lines:
        raise RuntimeError("Vellum logged startup errors: " + " | ".join(error_lines))
    print(json.dumps(result, indent=2, sort_keys=True))

    # The base directory is disposable, so bypass sync and close the local
    # collection explicitly instead of relying on application shutdown hooks.
    addon_app.stop()
    if mw.col is not None:
        mw.col.close()
        mw.col = None
    app.quit()
    app.processEvents()
    sys.stdout.flush()
    # QtWebEngine registers process-global atexit callbacks that can emit late
    # callback noise after the explicitly closed disposable collection. All
    # test-owned resources are closed above, so end the isolated child here.
    os._exit(0)


if __name__ == "__main__":
    main()
