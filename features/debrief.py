"""Independent Session Debrief lifecycle and Deck Browser completion surface."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from ..anki.hooks import HookRegistry
from ..core.config import VellumConfig
from ..core.encoding import encoded_payload
from ..core.events import EventBus
from ..notes.repository import MindNote
from ..sessions.debrief import DebriefRepository, SessionDebrief
from ..sessions.generated_decks import GeneratedDeckHistoryRepository
from ..sessions.manager import SessionManager
from ..sessions.models import Session, SessionOrigin, TERMINAL_STATUSES
from ..ui.debrief import show_debrief, show_debrief_history
from .session_tracking import SessionTrackingModule


class DebriefModule:
    name = "session_debrief"

    def __init__(
        self,
        *,
        package_name: str,
        mw: Any,
        manager: SessionManager,
        tracking: SessionTrackingModule,
        repository: DebriefRepository,
        generated_decks: GeneratedDeckHistoryRepository,
        config: Callable[[], VellumConfig],
        events: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._package_name = package_name
        self._mw = mw
        self._manager = manager
        self._tracking = tracking
        self._repository = repository
        self._generated_decks = generated_decks
        self._config = config
        self._events = events
        self._logger = logger or logging.getLogger("vellum.features.debrief")
        self._hooks = HookRegistry(self._logger)
        self._unsubscribe: list[Callable[[], None]] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        self._tracking.start()
        self._mw.addonManager.setWebExports(
            self._package_name, r"ui/assets/.*\.(?:css|js)"
        )
        self._hooks.register(gui_hooks.webview_will_set_content, self._inject_assets)
        self._hooks.register(gui_hooks.deck_browser_did_render, self._render)
        self._hooks.register(
            gui_hooks.webview_did_receive_js_message, self._receive_message
        )
        self._unsubscribe.extend(
            (
                self._events.subscribe("session_finalized", self._finalize),
                self._events.subscribe("session_completed", self._normal_completed),
                self._events.subscribe("session_abandoned", self._normal_completed),
                self._events.subscribe("mind_note_created", self._note_created),
                self._events.subscribe("mind_notes_resurfaced", self._notes_resurfaced),
            )
        )
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._hooks.clear()
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        self._tracking.stop()
        self._running = False
        self._eval("window.VellumDebriefHome&&window.VellumDebriefHome.remove();")

    def _inject_assets(self, web_content: Any, context: object | None) -> None:
        if context is None or context.__class__.__name__ != "DeckBrowser":
            return
        package = self._mw.addonManager.addonFromModule(self._package_name)
        for collection, path in (
            (web_content.css, f"/_addons/{package}/ui/assets/vellum.css"),
            (web_content.js, f"/_addons/{package}/ui/assets/vellum.js"),
        ):
            if path not in collection:
                collection.append(path)

    def _normal_completed(self, session: Session) -> None:
        if session.origin is SessionOrigin.NORMAL and self._config().debrief.include_normal_sessions:
            self._finalize(session)

    def _finalize(self, session: Session) -> None:
        if not self._running or session.status not in TERMINAL_STATUSES:
            return
        try:
            debrief = self._repository.finalize(
                session,
                show_completion_card=self._config().debrief.show_completion_card,
                recovery_enabled=self._config().modules.recovery,
            )
            if debrief is not None and debrief.is_generated:
                if getattr(self._mw, "state", None) != "deckBrowser":
                    self._mw.moveToState("deckBrowser")
                else:
                    self._render(None)
        except Exception:
            self._logger.exception("Unable to finalize Session Debrief")

    def repair_terminal(self) -> int:
        repaired = 0
        for session_id in self._repository.terminal_sessions_without_debrief():
            session = self._manager.repository.get(session_id)
            if session is None:
                continue
            debrief = self._repository.finalize(
                session,
                show_completion_card=self._config().debrief.show_completion_card,
                recovery_enabled=self._config().modules.recovery,
            )
            repaired += int(debrief is not None)
        return repaired

    def _note_created(self, note: MindNote) -> None:
        self._record_note(note.id, "created")

    def _notes_resurfaced(self, notes: tuple[MindNote, ...]) -> None:
        for note in notes:
            self._record_note(note.id, "resurfaced")

    def _record_note(self, note_id: int, event_type: str) -> None:
        session = self._manager.current
        if session is None or session.status in TERMINAL_STATUSES:
            return
        try:
            self._repository.record_mind_note_event(session.id, note_id, event_type)
        except Exception:
            self._logger.exception("Unable to record Mind Note session event")

    def _render(self, _deck_browser: Any) -> None:
        if not self._running:
            return
        completion = self._repository.pending_completion()
        handoff = self._repository.active_handoff()
        payload = {
            "completion": self._compact(completion) if completion is not None else None,
            "handoff": (
                {
                    "sessionId": handoff.session_id,
                    "text": handoff.handoff_text,
                }
                if handoff is not None
                else None
            ),
            "theme": self._config().general.theme,
            "reducedMotion": self._config().general.reduced_motion
            or not self._config().general.animations,
        }
        self._eval(
            "window.VellumDebriefHome&&window.VellumDebriefHome.updateEncoded('"
            + encoded_payload(payload)
            + "');"
        )

    @staticmethod
    def _compact(debrief: SessionDebrief) -> dict[str, Any]:
        duration_ms = debrief.active_duration_ms
        seconds = (
            round(duration_ms / 1000)
            if duration_ms is not None
            else debrief.elapsed_seconds
        )
        return {
            "sessionId": debrief.session_id,
            "cards": debrief.unique_card_count,
            "seconds": seconds,
            "again": debrief.again_count,
            "hard": debrief.hard_count,
            "suggestion": str(debrief.suggestion.get("title") or "Done for now"),
        }

    def open(self, session_id: str | None = None) -> None:
        target = self._repository.get(session_id) if session_id else self._repository.pending_completion()
        if target is None:
            from aqt.utils import showInfo  # type: ignore[import-not-found]

            showInfo("No Session Debrief is available.", parent=self._mw)
            return
        self._repository.set_completion_state(target.session_id, "opened")
        history = self._generated_decks.get(target.session_id)

        def save_handoff(text: str) -> None:
            try:
                self._repository.save_handoff(target.session_id, text)
                from aqt.utils import tooltip  # type: ignore[import-not-found]

                tooltip("Handoff saved", parent=self._mw)
                self._render(None)
            except Exception as error:
                from aqt.utils import showWarning  # type: ignore[import-not-found]

                showWarning(str(error), parent=self._mw)

        suggestion = self._suggestion_callback(target)
        show_debrief(
            self._mw,
            target,
            history=history,
            handoff_enabled=self._config().debrief.handoff_enabled,
            on_save_handoff=save_handoff,
            on_suggestion=suggestion,
        )
        self._render(None)

    def _suggestion_callback(self, debrief: SessionDebrief) -> Callable[[], None] | None:
        kind = str(debrief.suggestion.get("kind") or "done")
        if kind == "recovery":
            def recover() -> None:
                module = self._mw_vellum_module("recovery")
                method = getattr(module, "open_topic", None)
                if callable(method):
                    method(
                        topic_id=str(debrief.suggestion.get("topic_id") or ""),
                        topic_label=str(debrief.suggestion.get("topic_label") or "Topic"),
                        topic_path=tuple(debrief.suggestion.get("topic_path") or ()),
                        raw_topic_tag=str(debrief.suggestion.get("raw_topic_tag") or ""),
                    )
            return recover
        if kind == "time_machine":
            def time_machine() -> None:
                module = self._mw_vellum_module("time_machine")
                method = getattr(module, "open", None)
                if callable(method):
                    method()
            return time_machine
        return None

    def _mw_vellum_module(self, name: str) -> Any:
        # Bootstrap attaches the application for UI-to-module navigation.
        app = getattr(self._mw, "_vellum_application", None)
        return app.services.modules.get(name) if app is not None else None

    def open_history(self) -> None:
        show_debrief_history(
            self._mw,
            self._repository.recent(200),
            self._generated_decks.recent(200),
            self._manager.repository.recent_terminal(200),
            open_debrief=self.open,
        )

    def _receive_message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ != "DeckBrowser":
            return handled
        prefixes = {
            "vellum:debrief:open:": self._open_message,
            "vellum:debrief:dismiss:": self._dismiss_message,
            "vellum:handoff:done:": self._handoff_done,
        }
        for prefix, callback in prefixes.items():
            if message.startswith(prefix):
                callback(message[len(prefix):])
                return (True, None)
        return handled

    def _open_message(self, session_id: str) -> None:
        self.open(session_id)

    def _dismiss_message(self, session_id: str) -> None:
        self._repository.set_completion_state(session_id, "dismissed")
        self._render(None)

    def _handoff_done(self, session_id: str) -> None:
        self._repository.acknowledge_handoff(session_id)
        self._render(None)

    def _eval(self, script: str) -> None:
        try:
            self._mw.web.eval(script)
        except Exception:
            self._logger.debug("Deck Browser unavailable for Debrief update")
