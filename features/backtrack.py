"""One-shortcut read-only return to the previous card or topic context."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import logging
import time
from typing import Any

from ..anki.card_context import build_card_context
from ..anki.hooks import HookRegistry
from ..anki.shortcuts import assign_shortcut
from ..continuity.backtrack import BacktrackEntry, select_backtrack
from ..core.config import VellumConfig
from ..topics.service import TopicService
from ..ui.backtrack import show_backtrack_dialog


class BacktrackModule:
    name = "backtrack"

    def __init__(
        self,
        mw: Any,
        topics: TopicService,
        config: Callable[[], VellumConfig],
        logger: logging.Logger | None = None,
    ) -> None:
        self._mw = mw
        self._topics = topics
        self._config = config
        self._logger = logger or logging.getLogger("vellum.features.backtrack")
        self._hooks = HookRegistry(self._logger)
        self._entries: deque[BacktrackEntry] = deque()
        self._action: Any | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        self._install_action()
        config = self._config()
        assign_shortcut(
            self._action,
            self._mw,
            config.backtrack.shortcut,
            enabled=(
                config.general.keyboard_shortcuts
                and config.backtrack.shortcut_enabled
            ),
            logger=self._logger,
            feature_name="Backtrack",
        )
        self._action.setEnabled(True)
        self._hooks.register(
            gui_hooks.reviewer_did_show_question, self._card_shown
        )
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._hooks.clear()
        self._entries.clear()
        if self._action is not None:
            self._action.setEnabled(False)
            self._action.setShortcut("")
        self._running = False

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Vellum Backtrack…", self._mw)
        qconnect(self._action.triggered, self.open)
        self._mw.addAction(self._action)

    def _entry(self, card: Any, shown_at: int | None = None) -> BacktrackEntry:
        context = build_card_context(card, self._topics)
        return BacktrackEntry(
            card_id=context.card_id,
            shown_at=int(time.time()) if shown_at is None else int(shown_at),
            topic_id=context.primary_topic_id,
            topic_label=(
                context.topic_path[-1] if context.topic_path else None
            ),
            topic_path=context.topic_path,
            source_badges=context.source_badges,
            raw_topic_tag=context.raw_topic_tag,
            deck_name=context.deck_name,
            state=context.state,
            lapses=context.lapses,
            reps=context.reps,
        )

    def _card_shown(self, card: Any) -> None:
        try:
            entry = self._entry(card)
            if self._entries and self._entries[-1].card_id == entry.card_id:
                self._entries[-1] = entry
            else:
                self._entries.append(entry)
            limit = self._config().backtrack.history_limit
            while len(self._entries) > limit:
                self._entries.popleft()
        except Exception:
            self._logger.exception("Unable to capture Backtrack context")

    def open(self) -> None:
        reviewer = getattr(self._mw, "reviewer", None)
        current = getattr(reviewer, "card", None)
        current_id = int(getattr(current, "id", 0) or 0)
        current_topic = None
        if current is not None:
            try:
                current_topic = build_card_context(
                    current, self._topics
                ).primary_topic_id
            except Exception:
                pass
        previous, previous_topic = select_backtrack(
            self._entries,
            current_card_id=current_id,
            current_topic_id=current_topic,
        )
        if previous is None:
            fallback = getattr(reviewer, "previous_card", None)
            if fallback is not None and int(getattr(fallback, "id", 0)) != current_id:
                try:
                    previous = self._entry(fallback)
                    previous_topic = previous
                except Exception:
                    self._logger.exception("Unable to read Anki's previous card")
        if previous is None:
            from aqt.utils import tooltip  # type: ignore[import-not-found]

            tooltip("No previous reviewer card yet", parent=self._mw)
            return
        previous_topic = previous_topic or previous
        show_backtrack_dialog(
            self._mw,
            self._mw,
            previous_card=previous,
            previous_topic=previous_topic,
        )
