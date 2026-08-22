"""Minimal deck-browser Home Panel with independent continuation entry points."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..anki.hooks import HookRegistry
from ..anki.topic_stats import collect_topic_stats
from ..core.config import VellumConfig
from ..core.encoding import encoded_payload
from ..core.events import EventBus
from ..sessions.manager import SessionManager
from ..sessions.models import Session, TERMINAL_STATUSES
from ..timing.model import TimingModel
from ..timing.models import TimingBucket
from ..anki.time_machine import collect_all_deck_queue
from ..topics.health import TopicHealthState, describe_topic_health
from ..topics.service import TopicService


@dataclass(frozen=True)
class HomeSnapshot:
    due_count: int
    estimated_seconds: float
    attention: tuple[tuple[str, str, str], ...]
    resumable: Session | None
    recent_labels: tuple[tuple[str, str], ...]


class HomeModule:
    name = "home_panel"

    def __init__(
        self,
        package_name: str,
        mw: Any,
        topics: TopicService,
        sessions: SessionManager,
        timing: TimingModel,
        config: Callable[[], VellumConfig],
        events: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._package_name = package_name
        self._mw = mw
        self._topics = topics
        self._sessions = sessions
        self._timing = timing
        self._config = config
        self._events = events
        self._logger = logger or logging.getLogger("vellum.features.home")
        self._hooks = HookRegistry(self._logger)
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
        self._hooks.register(gui_hooks.webview_will_set_content, self._inject_assets)
        self._hooks.register(gui_hooks.deck_browser_did_render, self._render)
        self._hooks.register(
            gui_hooks.webview_did_receive_js_message, self._receive_message
        )
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._hooks.clear()
        self._running = False
        try:
            self._mw.web.eval("window.VellumHome&&window.VellumHome.remove();")
        except Exception:
            pass

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

    def _render(self, _deck_browser: Any) -> None:
        if not self._running:
            return
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        config = self._config()
        def collect(collection: Any) -> HomeSnapshot:
            recent = self._topics.recent_topics(20)
            queued = collect_all_deck_queue(collection, fetch_limit=5000)
            attention: list[tuple[str, str, str]] = []
            if config.modules.topic_health and config.home.show_weak_topics:
                for parsed in recent[:8]:
                    if not parsed.raw_tag or not parsed.path:
                        continue
                    stats = collect_topic_stats(collection, parsed.raw_tag)
                    if stats.health_state in {
                        TopicHealthState.FADING.value,
                        TopicHealthState.NEEDS_RECOVERY.value,
                    }:
                        attention.append(
                            (
                                parsed.path[-1],
                                str(stats.health_state),
                                describe_topic_health(stats),
                            )
                        )
            due_count = int(
                queued.available_cards
            )
            counts = {
                TimingBucket.NEW: int(queued.counts[TimingBucket.NEW]),
                TimingBucket.LEARNING: int(queued.counts[TimingBucket.LEARNING]),
                TimingBucket.REVIEW: int(queued.counts[TimingBucket.REVIEW]),
            }
            resumable = self._sessions.repository.latest_resumable()
            if resumable is not None and resumable.status in TERMINAL_STATUSES:
                resumable = None
            return HomeSnapshot(
                due_count,
                self._timing.estimate_counts_seconds(counts),
                tuple(attention[:3]),
                resumable,
                tuple(
                    (parsed.topic_id, parsed.path[-1])
                    for parsed in recent
                    if parsed.topic_id and parsed.path
                ),
            )

        QueryOp(parent=self._mw, op=collect, success=self._show).failure(
            lambda error: self._logger.warning("Home Panel data unavailable: %s", error)
        ).run_in_background()

    def _show(self, snapshot: HomeSnapshot) -> None:
        if not self._running:
            return
        config = self._config()
        estimated_seconds = snapshot.estimated_seconds
        resumable = snapshot.resumable
        hour = time.localtime().tm_hour
        greeting = "Good morning." if hour < 12 else "Good afternoon." if hour < 18 else "Good evening."
        resume_payload = None
        if resumable is not None:
            total = resumable.estimated_total or resumable.starting_due_count
            remaining = max(0, total - resumable.reviewed_count) if total else None
            recent_labels = dict(snapshot.recent_labels)
            remaining_minutes = (
                max(
                    1,
                    round(
                        remaining
                        * self._timing.estimate_seconds(TimingBucket.REVIEW)
                        / 60
                    ),
                )
                if remaining
                else None
            )
            resume_payload = {
                "deck": resumable.deck_name or "Previous session",
                "reviewed": resumable.reviewed_count,
                "total": total,
                "remaining": remaining,
                "remainingMinutes": remaining_minutes,
                "lastTopic": recent_labels.get(resumable.last_topic_id),
            }
        payload = {
            "greeting": greeting if config.home.show_greeting else None,
            "due": snapshot.due_count,
            "estimatedMinutes": round(estimated_seconds / 60),
            "showEstimatedWorkload": config.home.show_estimated_workload
            and config.time_machine.show_estimates_on_deck,
            "showContinue": config.home.show_continue
            and config.resume.show_on_home
            and config.modules.resume,
            "resume": resume_payload,
            "showTimeMachine": config.home.show_time_machine
            and config.modules.time_machine,
            "presets": list(config.time_machine.presets_minutes),
            "showAttention": config.home.show_weak_topics
            and config.modules.topic_health,
            "attention": [
                {"label": label, "state": state, "reason": reason}
                for label, state, reason in snapshot.attention
            ],
            "theme": config.general.theme,
            "reducedMotion": config.general.reduced_motion
            or not config.general.animations,
        }
        encoded = encoded_payload(payload)
        try:
            self._mw.web.eval(
                "window.VellumHome&&window.VellumHome.updateEncoded('" + encoded + "');"
            )
        except Exception:
            self._logger.debug("Deck Browser WebView unavailable for Home Panel")

    def _receive_message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ != "DeckBrowser":
            return handled
        if message == "vellum:home:resume":
            self._events.emit("resume_requested")
            return (True, None)
        prefix = "vellum:home:time:"
        if message.startswith(prefix):
            if message == "vellum:home:time:custom":
                self._events.emit("time_machine_open_requested")
                return (True, None)
            try:
                minutes = int(message[len(prefix) :])
            except ValueError:
                return (True, None)
            if minutes in self._config().time_machine.presets_minutes:
                self._events.emit("time_machine_requested", minutes)
            return (True, None)
        return handled
