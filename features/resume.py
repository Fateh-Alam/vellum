"""Resume discovery, assessment, UI, and safe deck continuation."""

from __future__ import annotations

import logging
from dataclasses import replace
from collections.abc import Callable
from typing import Any

from ..anki.topic_stats import quote_search_value
from ..core.config import VellumConfig
from ..core.events import EventBus
from ..continuity.activity import ActivityRepository
from ..sessions.manager import SessionManager
from ..sessions.generated_decks import GeneratedDeckHistoryRepository
from ..sessions.models import Session, SessionOrigin
from ..sessions.resume import ResumePlanner
from ..topics.service import TopicService
from ..timing.model import TimingModel
from ..ui.resume import show_resume_dialog
from .session_tracking import SessionTrackingModule


class ResumeModule:
    name = "resume"

    def __init__(
        self,
        mw: Any,
        manager: SessionManager,
        topics: TopicService,
        config: Callable[[], VellumConfig],
        timing: TimingModel | None = None,
        tracking: SessionTrackingModule | None = None,
        events: EventBus | None = None,
        generated_decks: GeneratedDeckHistoryRepository | None = None,
        activity: ActivityRepository | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._mw = mw
        self._manager = manager
        self._config = config
        self._logger = logger or logging.getLogger("vellum.features.resume")
        self._tracking = tracking or SessionTrackingModule(
            manager, topics, timing=timing, logger=self._logger
        )
        self._action: Any | None = None
        self._running = False
        self._prompted = False
        self._unsubscribe: Callable[[], None] | None = None
        self._events = events
        self._generated_decks = generated_decks
        self._activity = activity

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._tracking.start()
        self._install_action()
        self._action.setEnabled(True)
        self._running = True
        if self._events is not None:
            self._unsubscribe = self._events.subscribe(
                "resume_requested", lambda: self.request_resume(False)
            )
        config = self._config()
        ramp_owns_launch = bool(
            self._activity is not None
            and config.modules.return_ramp
            and config.return_ramp.show_on_launch
            and self._activity.ramp_due(config.return_ramp.absence_days)
        )
        if config.resume.show_on_launch and not ramp_owns_launch and not self._prompted:
            self._prompted = True
            self._mw.progress.single_shot(600, lambda: self.request_resume(True), False)

    def stop(self) -> None:
        if not self._running:
            return
        self._tracking.stop()
        if self._action is not None:
            self._action.setEnabled(False)
        self._running = False
        self._prompted = False
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Resume Last Vellum Session…", self._mw)
        qconnect(self._action.triggered, lambda: self.request_resume(False))
        self._mw.addAction(self._action)

    def request_resume(self, automatic: bool = False) -> None:
        if not self._running:
            return
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def inspect(
            collection: Any,
        ) -> tuple[Session, int | None, bool] | None:
            session = (
                self._manager.repository.latest_generated_resumable()
                or self._manager.repository.latest_resumable()
            )
            if session is None:
                return None
            if session.deck_id is None or not session.deck_name:
                return (session, None, False)
            if collection.decks.name_if_exists(session.deck_id) != session.deck_name:
                return (session, None, False)
            query = f"deck:{quote_search_value(session.deck_name)} is:due"
            try:
                return (session, len(collection.find_cards(query)), True)
            except Exception:
                return (session, None, True)

        def show(snapshot: tuple[Session, int | None, bool] | None) -> None:
            if snapshot is None:
                if not automatic:
                    from aqt.utils import tooltip  # type: ignore[import-not-found]

                    tooltip("No unfinished Vellum session", parent=self._mw)
                return
            session, current_due, deck_available = snapshot
            config = self._config()
            assessed_session = (
                session if deck_available else replace(session, deck_id=None)
            )
            plan = ResumePlanner(config.resume.stale_after_days).assess(
                assessed_session, current_due
            )
            show_resume_dialog(
                self._mw,
                plan,
                on_resume=lambda: self._resume(assessed_session),
                on_abandon=lambda: self._abandon(session),
            )

        QueryOp(parent=self._mw, op=inspect, success=show).failure(
            lambda error: self._logger.warning(
                "Resume deck assessment failed: %s", error
            )
        ).run_in_background()

    def _resume(self, session: Session) -> None:
        if session.deck_id is None:
            from aqt.utils import showWarning  # type: ignore[import-not-found]

            showWarning("The original deck is no longer available.", parent=self._mw)
            return
        from aqt.operations.deck import set_current_deck  # type: ignore[import-not-found]

        def selected(_changes: Any) -> None:
            self._manager.resume(session.id)
            self._mw.moveToState("review")

        def failed(error: Exception) -> None:
            self._logger.warning("Resume deck selection failed: %s", error)
            from aqt.utils import showWarning  # type: ignore[import-not-found]

            showWarning(
                "Vellum could not reopen the saved deck. It may have been renamed "
                "or deleted.",
                parent=self._mw,
            )

        set_current_deck(parent=self._mw, deck_id=session.deck_id).success(
            selected
        ).failure(failed).run_in_background()

    def _abandon(self, session: Session) -> None:
        if session.origin in {
            SessionOrigin.TIME_MACHINE,
            SessionOrigin.RECOVERY,
        }:
            self._abandon_generated(session)
            return
        self._manager.abandon_saved(session.id)
        from aqt.utils import tooltip  # type: ignore[import-not-found]

        tooltip("Previous Vellum session abandoned", parent=self._mw)

    def _abandon_generated(self, session: Session) -> None:
        """End a saved generated session only after its owned deck is gone."""

        if self._generated_decks is None:
            self._warn_generated_cleanup(
                RuntimeError("generated deck history service is unavailable")
            )
            return
        if session.deck_id is None or not session.deck_name:
            self._generated_decks.mark_removed(
                session.id, reason="already_missing"
            )
            self._finish_abandon(session.id)
            return

        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        deck_id = session.deck_id
        deck_name = session.deck_name

        def inspect(collection: Any) -> str:
            actual_name = collection.decks.name_if_exists(deck_id)
            if actual_name is None:
                return "missing"
            if (
                actual_name == deck_name
                and bool(collection.decks.is_filtered(deck_id))
            ):
                return "owned"
            return "mismatch"

        def checked(result: str) -> None:
            if result == "missing":
                self._generated_decks.mark_removed(
                    session.id, reason="already_missing"
                )
                self._finish_abandon(session.id)
                return
            if result != "owned":
                self._warn_generated_cleanup(
                    RuntimeError("saved filtered deck identity no longer matches")
                )
                return
            from aqt.operations.deck import remove_decks  # type: ignore[import-not-found]

            def removed(_changes: Any) -> None:
                self._generated_decks.mark_removed(
                    session.id, reason="abandoned"
                )
                self._finish_abandon(session.id)

            remove_decks(
                parent=self._mw,
                deck_ids=[deck_id],
                deck_name=deck_name,
            ).success(removed).failure(
                self._warn_generated_cleanup
            ).run_in_background()

        QueryOp(parent=self._mw, op=inspect, success=checked).failure(
            self._warn_generated_cleanup
        ).run_in_background()

    def _finish_abandon(self, session_id: str) -> None:
        self._manager.abandon_saved(session_id)
        from aqt.utils import tooltip  # type: ignore[import-not-found]

        tooltip(
            "Previous Vellum session abandoned; temporary deck removed",
            parent=self._mw,
        )

    def _warn_generated_cleanup(self, error: Exception) -> None:
        self._logger.warning("Generated session cleanup failed: %s", error)
        from aqt.utils import showWarning  # type: ignore[import-not-found]

        showWarning(
            "Vellum kept this session unfinished because it could not safely "
            "verify and remove the exact temporary filtered deck. " + str(error),
            parent=self._mw,
        )
