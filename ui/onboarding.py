"""Versioned guided onboarding and a non-blocking upgrade invitation."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, Iterable

from ..anki.commands import command_views
from ..core.config import ModuleFlags
from ..core.encoding import encoded_payload
from .help import PRIVACY_PROMISE, PRODUCT_PROMISE
from ..topics.normalization import (
    is_anking_container,
    is_probably_utility_root,
    source_key,
    split_hierarchical_tag,
)


ONBOARDING_VERSION = 2


MODULE_COPY = {
    "context": ("Context", "See where the current card belongs."),
    "recovery": ("Recovery", "Repair the broader topic exposed by one card."),
    "time_machine": ("Time Machine", "Plan by the time you actually have."),
    "hud": ("Session HUD", "Keep quiet progress visible while reviewing."),
    "resume": ("Resume", "Continue interrupted study without false promises."),
    "return_ramp": ("Return Ramp", "Ease back in after an absence."),
    "backtrack": ("Backtrack", "Revisit the previous card read-only."),
    "mind_notes": ("Mind Notes", "Leave private thoughts on a topic."),
    "session_debrief": ("Session Debrief", "Understand what happened after a session."),
    "topic_health": ("Topic Health", "Optional recent-performance heuristic."),
    "home_panel": ("Home Panel", "Keep continuity controls on the deck screen."),
}


def detect_likely_roots(
    tags: Iterable[str], preferred_roots: tuple[str, ...]
) -> tuple[str, ...]:
    preferred = {source_key(root): root for root in preferred_roots}
    found: list[str] = []
    generic: Counter[str] = Counter()
    for tag in tags:
        segments = split_hierarchical_tag(str(tag))
        for segment in segments:
            root = preferred.get(source_key(segment))
            if root is not None and root not in found:
                found.append(root)
        if len(segments) > 1:
            first = segments[0]
            if not is_anking_container(first) and not is_probably_utility_root(first):
                generic[first] += 1
    ordered = sorted(found, key=preferred_roots.index)
    if ordered:
        return tuple(ordered)
    return tuple(
        root
        for root, _count in sorted(
            generic.items(), key=lambda item: (-item[1], item[0].casefold())
        )[:6]
    )


def should_auto_open(config: Any) -> bool:
    return (
        not config.onboarding_completed
        and config.onboarding_version < ONBOARDING_VERSION
        and config.onboarding_invitation_version < ONBOARDING_VERSION
    )


def should_offer_invitation(config: Any) -> bool:
    return (
        config.onboarding_completed
        and config.onboarding_version < ONBOARDING_VERSION
        and config.onboarding_invitation_version < ONBOARDING_VERSION
    )


def _load_roots(mw: Any, app: Any, callback: Any) -> None:
    from aqt.operations import QueryOp  # type: ignore[import-not-found]

    preferred = app.config.topic_parsing.preferred_roots
    QueryOp(
        parent=mw,
        op=lambda collection: detect_likely_roots(collection.tags.all(), preferred),
        success=callback,
    ).failure(lambda _error: callback(())).run_in_background()


def open_onboarding(mw: Any, app: Any) -> None:
    _load_roots(mw, app, lambda roots: show_onboarding(mw, app, roots))


def schedule_onboarding(mw: Any, app: Any) -> None:
    config = app.config
    if should_auto_open(config):
        open_onboarding(mw, app)
    elif should_offer_invitation(config):
        controller = getattr(mw, "_vellum_onboarding_controller", None)
        if controller is None:
            controller = OnboardingInvitationController(mw, app)
            setattr(mw, "_vellum_onboarding_controller", controller)
        controller.start()


def show_onboarding(mw: Any, app: Any, detected_roots: tuple[str, ...]) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
        qconnect,
    )

    config = app.config
    dialog = QDialog(mw)
    dialog.setWindowTitle("Getting Started with Vellum")
    dialog.setMinimumSize(820, 650)
    outer = QVBoxLayout(dialog)

    def secondary(label: Any) -> None:
        """Use the active theme's text color at reduced opacity.

        Anki's macOS dark palette can expose its mid role as near-black,
        so secondary copy must derive from the readable WindowText role.
        """

        from .theme import apply_secondary_text

        apply_secondary_text(label)

    brand = QLabel("VELLUM")
    brand.setStyleSheet("font-size: 11px; font-weight: 750; letter-spacing: 2px;")
    outer.addWidget(brand)
    progress = QLabel()
    secondary(progress)
    outer.addWidget(progress)
    pages = QStackedWidget()
    outer.addWidget(pages, 1)

    def page(title: str, intro: str) -> tuple[Any, Any]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 25px; font-weight: 650;")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        copy = QLabel(intro)
        copy.setWordWrap(True)
        copy.setStyleSheet("font-size: 14px; margin-bottom: 12px;")
        layout.addWidget(copy)
        scroll.setWidget(content)
        pages.addWidget(scroll)
        return content, layout

    _welcome, welcome_layout = page(
        "Anki remembers your cards. Vellum remembers your studying.",
        PRODUCT_PROMISE,
    )
    for title, copy in (
        ("Know where you are", "Context places a card inside its larger topic."),
        ("Recover the real gap", "Recovery turns one failure into a deliberate topic repair."),
        ("Plan from available time", "Time Machine builds only the bounded queue you chose."),
        ("Leave with meaning", "Debrief records patterns and an optional handoff to your future self."),
    ):
        block = QLabel(f"<b>{title}</b><br>{copy}")
        block.setWordWrap(True)
        block.setStyleSheet("padding: 10px; border: 1px solid palette(midlight);")
        welcome_layout.addWidget(block)
    privacy = QLabel(PRIVACY_PROMISE)
    privacy.setStyleSheet("margin-top: 12px;")
    secondary(privacy)
    privacy.setWordWrap(True)
    welcome_layout.addWidget(privacy)
    welcome_layout.addStretch(1)

    _setup, setup_layout = page(
        "Choose your setup",
        "The recommended setup keeps every continuity workflow available while "
        "leaving Topic Health—an explicitly approximate heuristic—opt-in.",
    )
    setup_scroll = QScrollArea()
    setup_scroll.setWidgetResizable(True)
    setup_body = QWidget()
    setup_body_layout = QVBoxLayout(setup_body)
    recommended = QPushButton("Use Recommended Setup")
    setup_body_layout.addWidget(recommended)
    module_boxes: dict[str, Any] = {}
    for name, (label, explanation) in MODULE_COPY.items():
        box = QCheckBox(label)
        box.setChecked(config.modules.enabled(name))
        box.setToolTip(explanation)
        module_boxes[name] = box
        setup_body_layout.addWidget(box)
        detail = QLabel(explanation)
        detail.setStyleSheet("margin-left: 22px;")
        secondary(detail)
        detail.setWordWrap(True)
        setup_body_layout.addWidget(detail)
    setup_body_layout.addStretch(1)
    setup_scroll.setWidget(setup_body)
    setup_layout.addWidget(setup_scroll, 1)

    def use_recommended() -> None:
        for name, box in module_boxes.items():
            box.setChecked(name != "topic_health")

    qconnect(recommended.clicked, use_recommended)

    _topics, topics_layout = page(
        "Connect your topic hierarchy",
        "Vellum detected likely roots from Anki’s local tag index. It did not read "
        "card question or answer text. Choose the root that should receive first priority.",
    )
    root = QComboBox()
    roots: list[str] = []
    for value in (*detected_roots, *config.topic_parsing.preferred_roots):
        if value and value not in roots:
            roots.append(value)
            root.addItem(value, value)
    topics_layout.addWidget(QLabel("Primary topic root"))
    topics_layout.addWidget(root)
    detected = QLabel(
        "Detected: " + ", ".join(detected_roots)
        if detected_roots
        else "No likely hierarchy was detected. Existing generic parsing remains available."
    )
    detected.setWordWrap(True)
    detected.setStyleSheet("margin-top: 8px;")
    secondary(detected)
    topics_layout.addWidget(detected)
    topics_layout.addStretch(1)

    _commands, commands_layout = page(
        "Learn the commands",
        "Labels use this computer’s native keyboard notation. Reviewer shortcuts "
        "are conflict-checked when Reviewer opens; Vellum never overrides another action.",
    )
    commands_table = QTableWidget()
    commands_table.setColumnCount(4)
    commands_table.setHorizontalHeaderLabels(("Command", "Shortcut", "Where", "Status"))
    commands_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    commands_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    commands_table.verticalHeader().setVisible(False)
    commands_layout.addWidget(commands_table, 1)

    _ready, ready_layout = page(
        "You’re ready",
        "Start with one real workflow. Review normally and open Context when you need "
        "orientation, Recovery when a broader gap appears, or Time Machine when time is limited.",
    )
    ready_summary = QLabel()
    ready_summary.setWordWrap(True)
    ready_summary.setStyleSheet("font-size: 15px; padding: 14px; border: 1px solid palette(midlight);")
    ready_layout.addWidget(ready_summary)
    paths = QLabel(
        "Available anytime:\n"
        "• Vellum → Commands & Help…\n"
        "• Vellum → Getting Started…\n"
        "• Tools → Vellum Settings…"
    )
    paths.setWordWrap(True)
    ready_layout.addWidget(paths)
    # Avoid ampersands here: Qt treats them as mnemonic markers, which can turn
    # human labels into platform-specific underscore artifacts.
    ready_time_machine = QPushButton("Finish, then Start Time Machine")
    ready_settings = QPushButton("Finish, then Open Settings")
    ready_help = QPushButton("Finish, then Open Guide")
    ready_layout.addWidget(ready_time_machine)
    ready_layout.addWidget(ready_settings)
    ready_layout.addWidget(ready_help)
    ready_layout.addStretch(1)

    controls = QHBoxLayout()
    later = QPushButton("Set Up Later")
    back = QPushButton("Back")
    next_button = QPushButton("Continue")
    controls.addWidget(later)
    controls.addStretch(1)
    controls.addWidget(back)
    controls.addWidget(next_button)
    outer.addLayout(controls)
    decided = {"value": False}

    def proposed_flags() -> ModuleFlags:
        return ModuleFlags(**{name: box.isChecked() for name, box in module_boxes.items()})

    def refresh_commands() -> None:
        proposed = replace(config, modules=proposed_flags())
        values = command_views(proposed, mw)
        commands_table.setRowCount(len(values))
        for row_index, command in enumerate(values):
            for column, value in enumerate(
                (command.name, command.native_shortcut, command.scope, command.status)
            ):
                commands_table.setItem(row_index, column, QTableWidgetItem(value))
        commands_table.resizeColumnsToContents()

    def refresh() -> None:
        index = pages.currentIndex()
        progress.setText(f"STEP {index + 1} OF {pages.count()}")
        back.setEnabled(index > 0)
        next_button.setText("Finish Setup" if index == pages.count() - 1 else "Continue")
        if index == 3:
            refresh_commands()
        if index == 4:
            enabled_names = [
                MODULE_COPY[name][0]
                for name, enabled in proposed_flags().__dict__.items()
                if enabled
            ]
            selected = root.currentData()
            ready_summary.setText(
                f"{len(enabled_names)} modules enabled"
                + (f" · {selected} is your first topic priority" if selected else "")
                + ". You can change everything later in Settings."
            )

    def go_back() -> None:
        pages.setCurrentIndex(max(0, pages.currentIndex() - 1))
        refresh()

    def finish_setup() -> None:
        current = app.config
        ordered = list(current.topic_parsing.preferred_roots)
        selected = root.currentData()
        if selected in ordered:
            ordered.remove(selected)
        if selected:
            ordered.insert(0, selected)
        app.apply_config(
            replace(
                current,
                config_version=2,
                onboarding_completed=True,
                onboarding_version=ONBOARDING_VERSION,
                onboarding_invitation_version=ONBOARDING_VERSION,
                modules=proposed_flags(),
                topic_parsing=replace(
                    current.topic_parsing, preferred_roots=tuple(ordered)
                ),
            )
        )
        decided["value"] = True
        dialog.accept()

    def continue_or_finish() -> None:
        if pages.currentIndex() < pages.count() - 1:
            pages.setCurrentIndex(pages.currentIndex() + 1)
            refresh()
            return
        finish_setup()

    def finish_then(destination: str) -> None:
        finish_setup()
        if destination == "time_machine":
            module = app.services.modules.get("time_machine")
            open_time_machine = getattr(module, "open", None)
            if callable(open_time_machine) and getattr(module, "running", False):
                open_time_machine()
        elif destination == "settings":
            app.services.events.emit("settings_requested", "General")
        else:
            from .help import show_help

            show_help(mw, app, initial_section="Start Here")

    def set_up_later() -> None:
        current = app.config
        app.apply_config(
            replace(
                current,
                config_version=2,
                onboarding_invitation_version=ONBOARDING_VERSION,
            )
        )
        decided["value"] = True
        dialog.reject()

    qconnect(back.clicked, go_back)
    qconnect(next_button.clicked, continue_or_finish)
    qconnect(later.clicked, set_up_later)
    qconnect(ready_time_machine.clicked, lambda: finish_then("time_machine"))
    qconnect(ready_settings.clicked, lambda: finish_then("settings"))
    qconnect(ready_help.clicked, lambda: finish_then("help"))
    refresh()
    dialog.exec()
    if not decided["value"]:
        set_up_later()

    controller = getattr(mw, "_vellum_onboarding_controller", None)
    if controller is not None:
        controller.stop()


class OnboardingInvitationController:
    def __init__(self, mw: Any, app: Any) -> None:
        self._mw = mw
        self._app = app
        self._registered = False

    def start(self) -> None:
        if self._registered:
            self.render()
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        gui_hooks.webview_will_set_content.append(self._inject_assets)
        gui_hooks.deck_browser_did_render.append(self._render_hook)
        gui_hooks.webview_did_receive_js_message.append(self._message)
        self._registered = True
        self.render()

    def stop(self) -> None:
        if not self._registered:
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        for hook, callback in (
            (gui_hooks.webview_will_set_content, self._inject_assets),
            (gui_hooks.deck_browser_did_render, self._render_hook),
            (gui_hooks.webview_did_receive_js_message, self._message),
        ):
            try:
                hook.remove(callback)
            except ValueError:
                pass
        self._registered = False
        try:
            self._mw.web.eval("window.VellumOnboardingInvite&&window.VellumOnboardingInvite.remove();")
        except Exception:
            pass

    def _inject_assets(self, web_content: Any, context: object | None) -> None:
        if context is None or context.__class__.__name__ != "DeckBrowser":
            return
        package = self._mw.addonManager.addonFromModule(self._app.package_name)
        for collection, path in (
            (web_content.css, f"/_addons/{package}/ui/assets/vellum.css"),
            (web_content.js, f"/_addons/{package}/ui/assets/vellum.js"),
        ):
            if path not in collection:
                collection.append(path)

    def _render_hook(self, _deck_browser: Any) -> None:
        self.render()

    def render(self) -> None:
        if not self._registered or not should_offer_invitation(self._app.config):
            return
        payload = encoded_payload(
            {
                "title": "Vellum has a new guided setup",
                "copy": "Meet Session Debrief, review your native commands, and reconnect topic parsing without changing your current setup unless you finish the tour.",
            }
        )
        try:
            self._mw.web.eval(
                "window.VellumOnboardingInvite&&window.VellumOnboardingInvite.updateEncoded('"
                + payload
                + "');"
            )
        except Exception:
            pass

    def _message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ != "DeckBrowser":
            return handled
        if message == "vellum:onboarding:start":
            open_onboarding(self._mw, self._app)
            return (True, None)
        if message == "vellum:onboarding:not-now":
            current = self._app.config
            self._app.apply_config(
                replace(
                    current,
                    config_version=2,
                    onboarding_invitation_version=ONBOARDING_VERSION,
                )
            )
            self.stop()
            return (True, None)
        return handled
