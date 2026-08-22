"""Reviewer Context sidebar integration over supported Anki hooks."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import Any

from ..anki.card_context import build_card_context
from ..anki.hooks import HookRegistry
from ..anki.topic_stats import collect_topic_stats
from ..anki.shortcuts import append_state_shortcut
from ..core.config import VellumConfig
from ..core.events import EventBus
from ..core.encoding import encoded_payload
from ..topics.models import CardContext
from ..topics.health import describe_topic_health
from ..topics.service import TopicService


TOPIC_ID = re.compile(r"^[0-9a-f]{40}$")


def context_payload(
    context: CardContext,
    config: VellumConfig,
    *,
    phase: str | None = None,
) -> dict[str, Any]:
    return {
        "topicId": context.primary_topic_id,
        "title": context.topic_path[-1] if context.topic_path else "No topic context",
        "path": list(context.topic_path),
        "ancestorIds": list(context.ancestor_topic_ids),
        "sourceBadges": list(context.source_badges)
        if config.context.show_source_badges
        else [],
        "side": config.context.side,
        "width": config.context.width,
        "defaultState": config.context.default_state,
        "phase": phase,
        "autoCollapse": config.context.auto_collapse_on_new_card,
        "pinned": config.context.pinned,
        "showTitle": config.context.show_title,
        "showBreadcrumbs": config.context.show_breadcrumbs,
        "showRecovery": config.modules.recovery and config.context.show_recovery,
        "showHealth": config.modules.topic_health and config.context.show_health,
        "showCardCount": config.context.show_card_count,
        "showMaturityBreakdown": config.context.show_maturity_breakdown,
        "showRetention": config.context.show_retention,
        "showRecentFailures": config.context.show_recent_failures,
        "collapseShortcut": (
            config.context.collapse_shortcut
            if config.general.keyboard_shortcuts
            else ""
        ),
        "reducedMotion": config.general.reduced_motion
        or not config.general.animations,
        "theme": config.general.theme,
    }


class ContextModule:
    name = "context"

    def __init__(
        self,
        package_name: str,
        mw: Any,
        topics: TopicService,
        config: Callable[[], VellumConfig],
        events: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._package_name = package_name
        self._mw = mw
        self._topics = topics
        self._config = config
        self._events = events
        self._logger = logger or logging.getLogger("vellum.features.context")
        self._hooks = HookRegistry(self._logger)
        self._running = False
        self._current_card_id: int | None = None
        self._current_topic_id: str | None = None
        self._current_raw_tag: str | None = None
        self._stats_inflight: set[str] = set()
        self._stats_cache: dict[str, tuple[float, Any]] = {}
        self._action: Any | None = None

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
        self._action.setShortcut("")
        self._action.setEnabled(True)
        self._hooks.register(gui_hooks.webview_will_set_content, self._inject_assets)
        self._hooks.register(gui_hooks.card_will_show, self._prepare_card)
        self._hooks.register(
            gui_hooks.webview_did_receive_js_message, self._receive_message
        )
        self._hooks.register(
            gui_hooks.state_shortcuts_will_change, self._state_shortcuts
        )
        self._running = True
        self._logger.info("Context sidebar enabled")

    def stop(self) -> None:
        if not self._running:
            return
        self._hooks.clear()
        self._running = False
        self._stats_inflight.clear()
        self._stats_cache.clear()
        if self._action is not None:
            self._action.setEnabled(False)
            self._action.setShortcut("")
        reviewer = getattr(self._mw, "reviewer", None)
        web = getattr(reviewer, "web", None)
        if web is not None:
            try:
                web.eval("window.VellumContext && window.VellumContext.remove();")
            except Exception:
                self._logger.debug("Reviewer WebView unavailable during Context shutdown")

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Toggle Vellum Context", self._mw)
        qconnect(self._action.triggered, self._toggle)
        self._mw.addAction(self._action)

    def _toggle(self) -> None:
        reviewer = getattr(self._mw, "reviewer", None)
        if reviewer is not None:
            reviewer.web.eval("window.VellumContext&&window.VellumContext.toggle();")

    def _state_shortcuts(self, state: str, shortcuts: list[tuple[Any, ...]]) -> None:
        if state != "review":
            return
        full_config = self._config()
        config = full_config.context
        append_state_shortcut(
            shortcuts,
            config.shortcut,
            self._toggle,
            enabled=full_config.general.keyboard_shortcuts
            and config.shortcut_enabled,
            logger=self._logger,
            feature_name="Context",
            owner=self._mw,
        )

    def _inject_assets(self, web_content: Any, context: object | None) -> None:
        if context is None or context.__class__.__name__ != "Reviewer":
            return
        addon_package = self._mw.addonManager.addonFromModule(self._package_name)
        css = f"/_addons/{addon_package}/ui/assets/vellum.css"
        js = f"/_addons/{addon_package}/ui/assets/vellum.js"
        if css not in web_content.css:
            web_content.css.append(css)
        if js not in web_content.js:
            web_content.js.append(js)

    def _prepare_card(self, text: str, card: Any, kind: str) -> str:
        if kind not in {"reviewQuestion", "reviewAnswer"}:
            return text
        try:
            card_context = build_card_context(card, self._topics)
            self._current_card_id = card_context.card_id
            self._current_topic_id = card_context.primary_topic_id
            self._current_raw_tag = card_context.raw_topic_tag
            payload = encoded_payload(
                context_payload(card_context, self._config(), phase=kind)
            )
            return (
                text
                + "<script>onUpdateHook.push(function(){"
                + "window.VellumContext&&window.VellumContext.updateEncoded('"
                + payload
                + "');});</script>"
            )
        except Exception:
            self._logger.exception("Unable to resolve Context for current card")
            return text

    def _request_topic_stats(self, topic_id: str) -> None:
        try:
            if (
                not TOPIC_ID.fullmatch(topic_id)
                or topic_id != self._current_topic_id
                or not self._current_raw_tag
                or topic_id in self._stats_inflight
            ):
                return
            card_id = self._current_card_id
            cached = self._stats_cache.get(topic_id)
            if cached is not None and time.monotonic() - cached[0] <= 60:
                self._deliver_topic_stats(card_id, topic_id, cached[1])
                return
            from aqt.operations import QueryOp  # type: ignore[import-not-found]

            def success(stats: Any) -> None:
                self._stats_inflight.discard(topic_id)
                self._stats_cache[topic_id] = (time.monotonic(), stats)
                self._deliver_topic_stats(card_id, topic_id, stats)

            def failure(error: Exception) -> None:
                self._stats_inflight.discard(topic_id)
                self._logger.warning("Context topic statistics unavailable: %s", error)

            self._stats_inflight.add(topic_id)
            raw_tag = self._current_raw_tag
            QueryOp(
                parent=self._mw,
                op=lambda collection: collect_topic_stats(collection, raw_tag),
                success=success,
            ).failure(failure).run_in_background()
        except Exception:
            self._logger.exception("Unable to load Context topic statistics")

    def _deliver_topic_stats(
        self,
        card_id: int | None,
        topic_id: str,
        stats: Any,
    ) -> None:
        if (
            self._current_card_id != card_id
            or self._current_topic_id != topic_id
            or not self._running
        ):
            return
        payload = encoded_payload(
            {
                "total": stats.total_cards,
                "new": stats.new_cards,
                "learning": stats.learning_cards,
                "review": stats.review_cards,
                "mature": stats.mature_cards,
                "due": stats.due_cards,
                "recentFailures": stats.recent_failures,
                "recentReviews": stats.recent_reviews,
                "retention": stats.retention_estimate,
                "health": stats.health_state,
                "healthReason": describe_topic_health(stats),
            }
        )
        reviewer = getattr(self._mw, "reviewer", None)
        if reviewer is not None:
            reviewer.web.eval(
                "window.VellumContext&&window.VellumContext.updateStatsEncoded('"
                + payload
                + "');"
            )

    def _receive_message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ != "Reviewer" or not message.startswith("vellum:"):
            return handled
        if message == "vellum:toggle_sidebar":
            context.web.eval("window.VellumContext&&window.VellumContext.toggle();")
            return (True, None)
        if message == "vellum:configure_topics":
            self._events.emit("settings_requested", "Topic Parsing")
            return (True, None)
        stats_prefix = "vellum:context_stats:"
        if message.startswith(stats_prefix):
            self._request_topic_stats(message[len(stats_prefix) :])
            return (True, None)
        prefix = "vellum:open_topic:"
        if message.startswith(prefix):
            value = message[len(prefix) :]
            if TOPIC_ID.fullmatch(value):
                self._events.emit("topic_open_requested", value)
            return (True, None)
        return handled
