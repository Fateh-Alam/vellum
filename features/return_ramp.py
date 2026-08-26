"""Configurable absence-aware re-entry over Study by Time and Resume."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..anki.time_machine import collect_all_deck_queue
from ..continuity.activity import ActivityRepository, ReturnActivity
from ..continuity.return_ramp import RampSuggestion, ReturnRampWorkload
from ..core.config import VellumConfig
from ..core.events import EventBus
from ..sessions.manager import SessionManager
from ..sessions.models import TERMINAL_STATUSES
from ..timing.model import TimingModel
from ..timing.models import TimingBucket
from ..ui.return_ramp import show_return_ramp_dialog
from .time_machine import queue_fetch_limit


class ReturnRampModule:
    name = "return_ramp"

    def __init__(
        self,
        mw: Any,
        activity: ActivityRepository,
        sessions: SessionManager,
        timing: TimingModel,
        config: Callable[[], VellumConfig],
        events: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._mw = mw
        self._activity = activity
        self._sessions = sessions
        self._timing = timing
        self._config = config
        self._events = events
        self._logger = logger or logging.getLogger("vellum.features.return_ramp")
        self._running = False
        self._action: Any | None = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._install_action()
        self._action.setEnabled(True)
        self._running = True
        config = self._config().return_ramp
        if config.show_on_launch:
            activity = self._activity.claim_ramp(config.absence_days)
            if activity is not None:
                self._mw.progress.single_shot(
                    900, lambda: self._load(activity), False
                )

    def stop(self) -> None:
        if not self._running:
            return
        if self._action is not None:
            self._action.setEnabled(False)
        self._running = False

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Open Vellum Return Ramp…", self._mw)
        qconnect(self._action.triggered, self.open)
        self._mw.addAction(self._action)

    def open(self) -> None:
        activity = self._activity.current
        absence = (
            activity.absence_seconds
            if activity is not None and activity.absence_seconds is not None
            else 0
        )
        self._load(
            ReturnActivity(
                opened_at=activity.opened_at if activity else 0,
                previous_opened_at=(activity.previous_opened_at if activity else None),
                previous_closed_at=(activity.previous_closed_at if activity else None),
                absence_seconds=absence,
            )
        )

    def _load(self, activity: ReturnActivity) -> None:
        if not self._running:
            return
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        config = self._config()
        minutes = tuple(
            config.time_machine.presets_minutes[:
                config.return_ramp.suggestion_count
            ]
        ) or (10, 20, 30)

        def collect(collection: Any) -> ReturnRampWorkload:
            fastest = min(
                self._timing.estimate_seconds(bucket) for bucket in TimingBucket
            )
            snapshot = collect_all_deck_queue(
                collection,
                fetch_limit=queue_fetch_limit(max(minutes), fastest),
            )
            suggestions = tuple(
                RampSuggestion(
                    minutes=value,
                    expected_cards=self._timing.estimate_session(
                        snapshot.buckets, value * 60
                    ).expected_cards,
                )
                for value in minutes
            )
            return ReturnRampWorkload(
                absence_seconds=int(activity.absence_seconds or 0),
                available_cards=snapshot.available_cards,
                active_decks=snapshot.active_decks,
                new_cards=snapshot.counts[TimingBucket.NEW],
                learning_cards=(
                    snapshot.counts[TimingBucket.LEARNING]
                    + snapshot.counts[TimingBucket.RELEARNING]
                ),
                review_cards=snapshot.counts[TimingBucket.REVIEW],
                estimated_minutes=max(
                    0,
                    round(
                        self._timing.estimate_counts_seconds(snapshot.counts) / 60
                    ),
                ),
                suggestions=suggestions,
            )

        QueryOp(parent=self._mw, op=collect, success=self._show).failure(
            self._failed
        ).run_in_background()

    def _show(self, workload: ReturnRampWorkload) -> None:
        if not self._running:
            return
        generated = self._sessions.repository.latest_generated_resumable()
        resumable = generated or self._sessions.repository.latest_resumable()
        resume_label = None
        if resumable is not None and resumable.status not in TERMINAL_STATUSES:
            count = resumable.estimated_total or resumable.starting_due_count
            suffix = f" · {count} cards planned" if count is not None else ""
            resume_label = f"{resumable.deck_name or 'Previous session'}{suffix}"
        config = self._config()
        show_return_ramp_dialog(
            self._mw,
            workload,
            resume_label=resume_label,
            generated_session_waiting=generated is not None,
            can_start_time_machine=config.modules.time_machine,
            on_resume=lambda: self._events.emit("resume_requested"),
            on_start=lambda minutes: self._events.emit(
                "time_machine_requested", minutes
            ),
        )

    def _failed(self, error: Exception) -> None:
        self._logger.warning("Return Ramp workload unavailable: %s", error)
        if self._sessions.repository.latest_resumable() is not None:
            self._events.emit("resume_requested")
