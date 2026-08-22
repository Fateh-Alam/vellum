"""One calm top-level Vellum menu over independent module entry points."""

from __future__ import annotations

from typing import Any


def install_vellum_menu(mw: Any, app: Any) -> Any:
    from aqt.qt import QAction, QMenu, qconnect  # type: ignore[import-not-found]
    from aqt.utils import askUser, showInfo, tooltip  # type: ignore[import-not-found]
    from ..sessions.models import SessionOrigin, TERMINAL_STATUSES
    from .settings import show_settings
    from .weak_topics import show_weak_topics

    menu = QMenu("Vellum", mw)

    def invoke(module_name: str, method_name: str, label: str) -> None:
        module = app.services.modules.get(module_name)
        if module is None or not module.running:
            showInfo(f"Enable {label} in Vellum Settings first.", parent=mw)
            return
        method = getattr(module, method_name, None)
        if callable(method):
            method()

    entries = (
        ("Resume Last Session", "resume", "request_resume", "Resume"),
        ("Return Ramp…", "return_ramp", "open", "Return Ramp"),
        ("Start Time Machine…", "time_machine", "open", "Time Machine"),
        ("Recover Current Topic", "recovery", "open", "Topic Recovery"),
        ("Backtrack…", "backtrack", "open", "Backtrack"),
        ("Add Mind Note…", "mind_notes", "open", "Mind Notes"),
        ("Toggle Context Sidebar", "context", "_toggle", "Context Sidebar"),
    )
    for text, module_name, method_name, label in entries:
        action = QAction(text, mw)
        qconnect(
            action.triggered,
            lambda _checked=False, m=module_name, method=method_name, shown=label: invoke(
                m, method, shown
            ),
        )
        menu.addAction(action)

    weak = QAction("Weak Topics…", mw)
    qconnect(weak.triggered, lambda: show_weak_topics(mw, app))
    menu.addAction(weak)
    history = QAction("Session History…", mw)

    def show_history() -> None:
        debrief = app.services.modules.get("session_debrief")
        open_history = getattr(debrief, "open_history", None)
        if callable(open_history) and getattr(debrief, "running", False):
            open_history()
            return
        from .history import show_generated_deck_history

        show_generated_deck_history(mw, app.services.generated_decks)

    qconnect(history.triggered, show_history)
    menu.addAction(history)
    note_history = QAction("Mind Notes History…", mw)
    qconnect(
        note_history.triggered,
        lambda: invoke("mind_notes", "open_history", "Mind Notes"),
    )
    menu.addAction(note_history)
    finish = QAction("Finish Current Session", mw)

    def finish_session() -> None:
        session = app.services.sessions.current
        if session is None or session.status in TERMINAL_STATUSES:
            tooltip("No active Vellum session", parent=mw)
            return
        if session.origin is SessionOrigin.RECOVERY:
            recovery = app.services.modules.get("recovery")
            finish_recovery = getattr(recovery, "finish_current", None)
            if callable(finish_recovery):
                finish_recovery()
                return
            showInfo(
                "Enable Topic Recovery to safely return its temporary cards.",
                parent=mw,
            )
            return
        if session.origin is SessionOrigin.TIME_MACHINE:
            time_machine = app.services.modules.get("time_machine")
            finish_time_machine = getattr(time_machine, "finish_current", None)
            if callable(finish_time_machine):
                finish_time_machine()
                return
            showInfo(
                "Enable Time Machine to safely return its temporary cards.",
                parent=mw,
            )
            return
        if not askUser(
            "Finish the current Vellum session? Anki scheduling changes already "
            "made by answered cards are preserved.",
            parent=mw,
        ):
            return
        app.services.sessions.complete()
        if getattr(mw, "state", None) == "review":
            mw.moveToState("overview")

    qconnect(finish.triggered, finish_session)
    menu.addAction(finish)
    menu.addSeparator()
    getting_started = QAction("Getting Started…", mw)
    from .onboarding import open_onboarding

    qconnect(getting_started.triggered, lambda: open_onboarding(mw, app))
    menu.addAction(getting_started)
    help_action = QAction("Commands && Help…", mw)
    from .help import show_help

    qconnect(help_action.triggered, lambda: show_help(mw, app, initial_section="Commands"))
    menu.addAction(help_action)
    about = QAction("About Vellum…", mw)

    def show_about() -> None:
        from ..core.release import VELLUM_HOMEPAGE, VELLUM_VERSION

        showInfo(
            f"Vellum {VELLUM_VERSION}\n\n"
            "A local-first study-continuity layer for Anki. Anki and FSRS "
            "remain authoritative. Vellum has no account, telemetry, cloud "
            "backend, or external data requests.\n\n"
            f"Source, support, and releases:\n{VELLUM_HOMEPAGE}",
            parent=mw,
            title="About Vellum",
        )

    qconnect(about.triggered, show_about)
    menu.addAction(about)
    menu.addSeparator()
    diagnostics = QAction("Diagnostics…", mw)
    qconnect(diagnostics.triggered, lambda: show_settings(mw, app, initial_tab="Data"))
    menu.addAction(diagnostics)
    settings = QAction("Settings…", mw)
    qconnect(settings.triggered, lambda: show_settings(mw, app))
    menu.addAction(settings)
    mw.menuBar().addMenu(menu)
    return menu
