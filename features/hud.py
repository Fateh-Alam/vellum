"""Independent, quiet reviewer HUD for normal and Time Machine sessions."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from ..anki.hooks import HookRegistry
from ..core.config import VellumConfig
from ..core.encoding import encoded_payload
from ..core.events import EventBus
from ..sessions.manager import SessionManager
from ..sessions.models import Session, SessionOrigin, TERMINAL_STATUSES
from .session_tracking import SessionTrackingModule


def hud_payload(session: Session, config: VellumConfig, now: int | None = None) -> dict[str, Any]:
    now = int(time.time()) if now is None else now
    elapsed = max(0, now - session.started_at)
    remaining = (
        max(0, session.target_seconds - elapsed)
        if session.target_seconds is not None
        else None
    )
    return {
        "sessionId": session.id,
        "reviewed": session.reviewed_count,
        "estimatedTotal": session.estimated_total,
        "startedAt": session.started_at,
        "targetSeconds": session.target_seconds,
        "elapsedSeconds": elapsed,
        "remainingSeconds": remaining,
        "placement": config.hud.placement,
        "showCompleted": config.hud.show_completed,
        "showEstimatedTotal": config.hud.show_estimated_total,
        "showElapsed": config.hud.show_elapsed,
        "showRemainingTime": config.hud.show_remaining_time,
        "showEta": config.hud.show_eta,
        "showCardsPerMinute": config.hud.show_cards_per_minute,
        "showSessionTarget": config.hud.show_session_target,
        "showProgressBar": config.hud.show_progress_bar,
        "endBehavior": config.time_machine.end_behavior,
        "theme": config.general.theme,
        "reducedMotion": config.general.reduced_motion
        or not config.general.animations,
    }


class HudModule:
    name = "hud"

    def __init__(
        self,
        package_name: str,
        mw: Any,
        manager: SessionManager,
        tracking: SessionTrackingModule,
        config: Callable[[], VellumConfig],
        events: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._package_name = package_name
        self._mw = mw
        self._manager = manager
        self._tracking = tracking
        self._config = config
        self._events = events
        self._logger = logger or logging.getLogger("vellum.features.hud")
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
        self._hooks.register(gui_hooks.reviewer_did_show_question, self._shown)
        # Reviewer question hooks render the live count after Anki has switched
        # cards. Avoid duplicate WebView evaluations inside the answer hook.
        for event in ("session_started", "session_resumed"):
            self._unsubscribe.append(self._events.subscribe(event, self._update))
        for event in ("session_completed", "session_interrupted", "session_abandoned"):
            self._unsubscribe.append(self._events.subscribe(event, self._hide))
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
        self._eval("window.VellumHUD&&window.VellumHUD.remove();")

    def _inject_assets(self, web_content: Any, context: object | None) -> None:
        if context is None or context.__class__.__name__ != "Reviewer":
            return
        package = self._mw.addonManager.addonFromModule(self._package_name)
        for collection, path in (
            (web_content.css, f"/_addons/{package}/ui/assets/vellum.css"),
            (web_content.js, f"/_addons/{package}/ui/assets/vellum.js"),
        ):
            if path not in collection:
                collection.append(path)

    def _shown(self, _card: Any) -> None:
        if self._manager.current is not None:
            self._update(self._manager.current)

    def _update(self, session: Session) -> None:
        if not self._running or session.status in TERMINAL_STATUSES:
            return
        if (
            session.origin is SessionOrigin.TIME_MACHINE
            and not self._config().time_machine.automatically_start_hud
        ):
            self._hide(session)
            return
        payload = encoded_payload(hud_payload(session, self._config()))
        self._eval(
            "window.VellumHUD&&window.VellumHUD.updateEncoded('" + payload + "');"
        )

    def _hide(self, _session: Session) -> None:
        self._eval("window.VellumHUD&&window.VellumHUD.hide();")

    def _eval(self, script: str) -> None:
        try:
            reviewer = getattr(self._mw, "reviewer", None)
            if reviewer is not None:
                reviewer.web.eval(script)
        except Exception:
            self._logger.debug("Reviewer WebView unavailable for HUD update")
