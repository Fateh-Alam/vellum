"""Topic-linked local notes that resurface in the Reviewer."""

from __future__ import annotations

from collections.abc import Callable
import logging
import time
from typing import Any

from ..anki.card_context import build_card_context
from ..anki.hooks import HookRegistry
from ..anki.shortcuts import assign_shortcut
from ..core.config import VellumConfig
from ..core.encoding import encoded_payload
from ..core.events import EventBus
from ..notes.repository import MindNote, MindNoteRepository
from ..topics.models import CardContext
from ..topics.service import TopicService
from ..ui.mind_notes import show_mind_note_editor, show_mind_note_history


def relative_age(created_at: int, now: int | None = None) -> str:
    current = int(time.time()) if now is None else int(now)
    seconds = max(0, current - int(created_at))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} {'minute' if minutes == 1 else 'minutes'} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} {'hour' if hours == 1 else 'hours'} ago"
    days = seconds // 86400
    return f"{days} {'day' if days == 1 else 'days'} ago"


def mind_note_payload(
    context: CardContext,
    notes: tuple[MindNote, ...],
    config: VellumConfig,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    return {
        "topicId": context.primary_topic_id,
        "topicLabel": context.topic_path[-1] if context.topic_path else "Topic",
        "theme": config.general.theme,
        "reducedMotion": config.general.reduced_motion
        or not config.general.animations,
        "notes": [
            {
                "id": note.id,
                "body": note.body,
                "age": relative_age(note.created_at, now),
            }
            for note in notes
        ],
    }


class MindNotesModule:
    name = "mind_notes"

    def __init__(
        self,
        package_name: str,
        mw: Any,
        topics: TopicService,
        repository: MindNoteRepository,
        config: Callable[[], VellumConfig],
        events: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._package_name = package_name
        self._mw = mw
        self._topics = topics
        self._repository = repository
        self._config = config
        self._events = events
        self._logger = logger or logging.getLogger("vellum.features.mind_notes")
        self._hooks = HookRegistry(self._logger)
        self._current_context: CardContext | None = None
        self._action: Any | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        self._mw.addonManager.setWebExports(
            self._package_name, r"ui/assets/.*\.(?:css|js)"
        )
        self._install_action()
        config = self._config()
        assign_shortcut(
            self._action,
            self._mw,
            config.mind_notes.shortcut,
            enabled=(
                config.general.keyboard_shortcuts
                and config.mind_notes.shortcut_enabled
            ),
            logger=self._logger,
            feature_name="Mind Notes",
        )
        self._action.setEnabled(True)
        self._hooks.register(
            gui_hooks.webview_will_set_content, self._inject_assets
        )
        self._hooks.register(
            gui_hooks.reviewer_did_show_question, self._card_shown
        )
        self._hooks.register(
            gui_hooks.webview_did_receive_js_message, self._receive_message
        )
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._hooks.clear()
        self._current_context = None
        if self._action is not None:
            self._action.setEnabled(False)
            self._action.setShortcut("")
        reviewer = getattr(self._mw, "reviewer", None)
        web = getattr(reviewer, "web", None)
        if web is not None:
            try:
                web.eval(
                    "window.VellumMindNotes&&window.VellumMindNotes.remove();"
                )
            except Exception:
                pass
        self._running = False

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Add Vellum Mind Note…", self._mw)
        qconnect(self._action.triggered, self.open)
        self._mw.addAction(self._action)

    def _inject_assets(self, web_content: Any, context: object | None) -> None:
        if context is None or context.__class__.__name__ != "Reviewer":
            return
        package = self._mw.addonManager.addonFromModule(self._package_name)
        css = f"/_addons/{package}/ui/assets/vellum.css"
        js = f"/_addons/{package}/ui/assets/vellum.js"
        if css not in web_content.css:
            web_content.css.append(css)
        if js not in web_content.js:
            web_content.js.append(js)

    def _card_shown(self, card: Any) -> None:
        try:
            context = build_card_context(card, self._topics)
            self._current_context = context
            self._mw.progress.single_shot(
                25,
                lambda card_id=context.card_id: self._deliver(card_id),
                False,
            )
        except Exception:
            self._logger.exception("Unable to resolve Mind Note topic")

    def _deliver(self, card_id: int) -> None:
        context = self._current_context
        if (
            not self._running
            or context is None
            or context.card_id != card_id
            or not context.primary_topic_id
        ):
            return
        config = self._config()
        notes = (
            self._repository.active_for_topic(
                context.primary_topic_id,
                limit=config.mind_notes.maximum_active_per_topic,
            )
            if config.mind_notes.resurface
            else ()
        )
        payload = encoded_payload(mind_note_payload(context, notes, config))
        reviewer = getattr(self._mw, "reviewer", None)
        web = getattr(reviewer, "web", None)
        if web is None:
            return
        web.eval(
            "window.VellumMindNotes&&window.VellumMindNotes.updateEncoded('"
            + payload
            + "');"
        )
        self._repository.mark_shown(tuple(note.id for note in notes))
        if notes:
            self._events.emit("mind_notes_resurfaced", notes)

    def open(self) -> None:
        context = self._current_context
        reviewer = getattr(self._mw, "reviewer", None)
        card = getattr(reviewer, "card", None)
        if card is not None and (
            context is None or context.card_id != int(getattr(card, "id", 0))
        ):
            try:
                context = build_card_context(card, self._topics)
                self._current_context = context
            except Exception:
                context = None
        if context is None or not context.primary_topic_id or not context.topic_path:
            from aqt.utils import showInfo  # type: ignore[import-not-found]

            showInfo(
                "Open a reviewer card with a parsed topic before adding a Mind Note.",
                parent=self._mw,
            )
            return

        def save(body: str) -> None:
            try:
                note = self._repository.create(
                    topic_id=str(context.primary_topic_id),
                    topic_label=context.topic_path[-1],
                    topic_path=context.topic_path,
                    body=body,
                    source_card_id=context.card_id,
                )
                self._events.emit("mind_note_created", note)
                self._deliver(context.card_id)
                from aqt.utils import tooltip  # type: ignore[import-not-found]

                tooltip(
                    f"Mind Note saved for {context.topic_path[-1]}",
                    parent=self._mw,
                )
            except Exception as error:
                self._logger.exception("Unable to save Mind Note")
                from aqt.utils import showWarning  # type: ignore[import-not-found]

                showWarning(f"Mind Note could not be saved: {error}", parent=self._mw)

        show_mind_note_editor(
            self._mw,
            topic_label=context.topic_path[-1],
            topic_path=context.topic_path,
            on_save=save,
        )

    def open_history(self) -> None:
        show_mind_note_history(self._mw, self._repository)

    def _receive_message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ != "Reviewer":
            return handled
        if message == "vellum:mind-note:add":
            self.open()
            return (True, None)
        prefix = "vellum:mind-note:resolve:"
        if not message.startswith(prefix):
            return handled
        try:
            note_id = int(message[len(prefix) :])
        except ValueError:
            return (True, None)
        note = self._repository.get(note_id)
        current = self._current_context
        if (
            note is not None
            and current is not None
            and note.topic_id == current.primary_topic_id
            and self._repository.resolve(note_id)
        ):
            self._deliver(current.card_id)
        return (True, None)
