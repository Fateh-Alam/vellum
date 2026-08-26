"""Time-box planning over Anki's idempotent scheduler queue snapshot."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from typing import Any

from ..anki.hooks import HookRegistry
from ..anki.time_machine import (
    AllDeckQueueSnapshot,
    TimeMachineDeckChoice,
    collect_all_deck_queue,
    collect_selected_deck_queue,
    create_time_machine_deck,
    list_time_machine_decks,
    queued_buckets,
)
from ..core.config import VellumConfig
from ..core.encoding import encoded_payload
from ..anki.shortcuts import assign_shortcut
from ..core.events import EventBus
from ..sessions.manager import SessionManager
from ..sessions.generated_decks import GeneratedDeckHistoryRepository
from ..sessions.models import Session, SessionOrigin, TERMINAL_STATUSES
from ..timing.model import TimingModel
from ..timing.models import SessionEstimate, TimingBucket
from ..ui.time_machine import (
    show_deck_selection_dialog,
    show_duration_dialog,
    show_estimate_dialog,
)
from .session_tracking import SessionTrackingModule


def time_target_reached(session: Session, now: int | None = None) -> bool:
    """Return true only for a live Study by Time session at or past its target."""

    if (
        session.origin is not SessionOrigin.TIME_MACHINE
        or session.target_seconds is None
        or session.status in TERMINAL_STATUSES
    ):
        return False
    current = int(time.time()) if now is None else now
    return current - session.started_at >= session.target_seconds


def queue_fetch_limit(minutes: int, fastest_seconds_per_card: float) -> int:
    """Fetch enough scheduler order for the chosen target without going unbounded."""

    fastest = max(0.25, float(fastest_seconds_per_card))
    needed = math.ceil(max(1, minutes) * 60 / fastest)
    return min(100_000, max(5_000, needed))


class TimeMachineModule:
    name = "time_machine"

    def __init__(
        self,
        package_name: str,
        mw: Any,
        manager: SessionManager,
        timing: TimingModel,
        tracking: SessionTrackingModule,
        config: Callable[[], VellumConfig],
        events: EventBus,
        generated_decks: GeneratedDeckHistoryRepository,
        logger: logging.Logger | None = None,
    ) -> None:
        self._package_name = package_name
        self._mw = mw
        self._manager = manager
        self._timing = timing
        self._tracking = tracking
        self._config = config
        self._events = events
        self._generated_decks = generated_decks
        self._logger = logger or logging.getLogger("vellum.features.time_machine")
        self._hooks = HookRegistry(self._logger)
        self._action: Any | None = None
        self._running = False
        self._unsubscribe: list[Callable[[], None]] = []
        self._target_notified: set[str] = set()

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
        self._hooks.register(
            gui_hooks.overview_will_render_content, self._overview_content
        )
        self._hooks.register(gui_hooks.overview_did_refresh, self._overview_refreshed)
        self._hooks.register(gui_hooks.webview_will_set_content, self._inject_assets)
        self._hooks.register(
            gui_hooks.webview_did_receive_js_message, self._receive_message
        )
        self._hooks.register(gui_hooks.reviewer_will_end, self._reviewer_ended)
        self._install_action()
        full_config = self._config()
        config = full_config.time_machine
        assign_shortcut(
            self._action,
            self._mw,
            config.shortcut,
            enabled=full_config.general.keyboard_shortcuts
            and config.shortcut_enabled,
            logger=self._logger,
            feature_name="Study by Time",
        )
        self._action.setEnabled(True)
        self._unsubscribe.append(
            self._events.subscribe("time_machine_requested", self._choose_decks)
        )
        self._unsubscribe.append(
            self._events.subscribe("time_machine_open_requested", self.open)
        )
        self._unsubscribe.append(
            self._events.subscribe("session_card_answered", self._target_update)
        )
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._tracking.stop()
        self._hooks.clear()
        if self._action is not None:
            self._action.setEnabled(False)
            self._action.setShortcut("")
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        self._target_notified.clear()
        self._running = False

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Plan a Timed Session…", self._mw)
        qconnect(self._action.triggered, self.open)
        self._mw.addAction(self._action)

    def open(self) -> None:
        saved = self._manager.repository.latest_generated_resumable()
        if saved is not None and saved.status not in TERMINAL_STATUSES:
            from aqt.utils import showInfo  # type: ignore[import-not-found]

            showInfo(
                "A Vellum-generated session is already unfinished. Resume, "
                "finish, or abandon it before creating another filtered deck.",
                parent=self._mw,
            )
            return
        config = self._config()
        show_duration_dialog(
            self._mw, config.time_machine.presets_minutes, self._choose_decks
        )

    def _inject_assets(self, web_content: Any, context: object | None) -> None:
        if context is None or context.__class__.__name__ != "Overview":
            return
        package = self._mw.addonManager.addonFromModule(self._package_name)
        for collection, path in (
            (web_content.css, f"/_addons/{package}/ui/assets/vellum.css"),
            (web_content.js, f"/_addons/{package}/ui/assets/vellum.js"),
        ):
            if path not in collection:
                collection.append(path)

    def _overview_content(self, _overview: Any, content: Any) -> None:
        config = self._config()
        presets = config.time_machine.presets_minutes
        buttons = "".join(
            '<button type="button" onclick="pycmd(\'vellum:overview:time:'
            + str(minutes)
            + "\')\">"
            + str(minutes)
            + "m</button>"
            for minutes in presets
        )
        content.table += (
            '<section id="vellum-overview" class="vellum-overview" data-theme="'
            + config.general.theme
            + '" '
            'aria-label="Vellum Study by Time">'
            '<div class="vellum-overview__copy"><strong>Study by Time</strong>'
            '<span id="vellum-overview-estimate">Plan all decks around your time.</span>'
            '</div><div class="vellum-overview__presets">'
            + buttons
            + '<button type="button" onclick="pycmd(\'vellum:overview:open\')">Custom…</button>'
            "</div></section>"
        )

    def _overview_refreshed(self, overview: Any) -> None:
        if not self._config().time_machine.show_estimates_on_deck:
            return
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def collect(
            collection: Any,
        ) -> tuple[int, float]:
            snapshot = collect_all_deck_queue(collection, fetch_limit=5000)
            return (
                snapshot.available_cards,
                self._timing.estimate_counts_seconds(snapshot.counts),
            )

        def success(snapshot: tuple[int, float]) -> None:
            count, seconds = snapshot
            payload = encoded_payload(
                {"cards": count, "minutes": max(0, round(seconds / 60))}
            )
            try:
                overview.web.eval(
                    "window.VellumOverview&&window.VellumOverview.updateEncoded('"
                    + payload
                    + "');"
                )
            except Exception:
                self._logger.debug("Deck Overview unavailable for Study by Time estimate")

        QueryOp(parent=self._mw, op=collect, success=success).failure(
            lambda error: self._logger.warning(
                "Study by Time deck estimate unavailable: %s", error
            )
        ).run_in_background()

    def _receive_message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ != "Overview":
            return handled
        if message == "vellum:overview:open":
            self.open()
            return (True, None)
        prefix = "vellum:overview:time:"
        if message.startswith(prefix):
            try:
                minutes = int(message[len(prefix) :])
            except ValueError:
                return (True, None)
            if minutes in self._config().time_machine.presets_minutes:
                self._choose_decks(minutes)
            return (True, None)
        return handled

    def _choose_decks(self, minutes: int) -> None:
        """Load a fresh checklist after every duration choice."""

        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def loaded(choices: tuple[TimeMachineDeckChoice, ...]) -> None:
            available = tuple(
                choice for choice in choices if choice.available_cards > 0
            )
            if not available:
                from aqt.utils import showInfo  # type: ignore[import-not-found]

                showInfo(
                    "No scheduler-available cards remain in any normal deck.",
                    parent=self._mw,
                )
                return
            show_deck_selection_dialog(
                self._mw,
                minutes,
                choices,
                lambda selected: self._estimate(
                    minutes,
                    selected,
                    all_available_ids=tuple(
                        choice.deck_id for choice in available
                    ),
                ),
            )

        QueryOp(
            parent=self._mw,
            op=list_time_machine_decks,
            success=loaded,
        ).failure(self._deck_selection_failed).run_in_background()

    def _deck_selection_failed(self, error: Exception) -> None:
        self._logger.warning("Study by Time deck selection unavailable: %s", error)
        from aqt.utils import showWarning  # type: ignore[import-not-found]

        showWarning(
            "Vellum could not load the deck checklist. No cards were changed. "
            + str(error),
            parent=self._mw,
        )

    def _estimate(
        self,
        minutes: int,
        selected_deck_ids: tuple[int, ...],
        *,
        all_available_ids: tuple[int, ...],
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        all_selected = set(selected_deck_ids) == set(all_available_ids)
        scope_label = "All decks" if all_selected else "Selected decks"
        session_query = (
            "all-decks"
            if all_selected
            else "deck-ids:" + ",".join(str(deck_id) for deck_id in selected_deck_ids)
        )

        def queue(
            collection: Any,
        ) -> tuple[AllDeckQueueSnapshot, SessionEstimate]:
            fastest = min(
                self._timing.estimate_seconds(bucket) for bucket in TimingBucket
            )
            fetch_limit = queue_fetch_limit(minutes, fastest)
            snapshot = collect_selected_deck_queue(
                collection,
                selected_deck_ids,
                fetch_limit=fetch_limit,
            )
            return (
                snapshot,
                self._timing.estimate_session(snapshot.buckets, minutes * 60),
            )

        def success(result: tuple[AllDeckQueueSnapshot, SessionEstimate]) -> None:
            snapshot, estimate = result
            show_estimate_dialog(
                self._mw,
                minutes,
                estimate,
                snapshot.available_cards,
                scope_label=scope_label,
                active_decks=snapshot.active_decks,
                truncated=snapshot.truncated,
                on_start=lambda: self._start_session(
                    minutes,
                    snapshot,
                    estimate.expected_cards,
                    estimate.estimated_seconds,
                    scope_label=scope_label,
                    session_query=session_query,
                ),
            )

        QueryOp(parent=self._mw, op=queue, success=success).failure(
            lambda error: self._estimate_failed(
                minutes,
                selected_deck_ids,
                scope_label,
                session_query,
                error,
            )
        ).run_in_background()

    def _estimate_failed(
        self,
        minutes: int,
        selected_deck_ids: tuple[int, ...],
        scope_label: str,
        session_query: str,
        error: Exception,
    ) -> None:
        """Degrade to the configured static review rate without blocking study."""

        self._logger.warning("Study by Time queue estimate failed: %s", error)
        seconds_per_card = self._config().time_machine.fallback_seconds.review
        expected = max(1, int(minutes * 60 / seconds_per_card))
        estimate = SessionEstimate(
            expected_cards=expected,
            estimated_seconds=expected * seconds_per_card,
            remaining_buffer_seconds=max(
                0.0, minutes * 60 - expected * seconds_per_card
            ),
            per_bucket={TimingBucket.REVIEW: expected},
            fallback_buckets=(TimingBucket.REVIEW,),
        )
        show_estimate_dialog(
            self._mw,
            minutes,
            estimate,
            None,
            scope_label=scope_label,
            active_decks=None,
            on_start=lambda: self._retry_start(
                minutes,
                selected_deck_ids,
                scope_label,
                session_query,
            ),
        )

    def _start_session(
        self,
        minutes: int,
        snapshot: AllDeckQueueSnapshot,
        expected_cards: int,
        estimated_seconds: float,
        *,
        scope_label: str,
        session_query: str,
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def create(collection: Any) -> Any:
            return create_time_machine_deck(
                collection,
                snapshot,
                minutes=minutes,
                card_limit=expected_cards,
            )

        def created(deck: Any) -> None:
            from aqt.operations.deck import set_current_deck  # type: ignore[import-not-found]

            def selected(_changes: Any) -> None:
                self._timing.reset_session_blend()
                session = self._manager.start(
                    deck_id=deck.deck_id,
                    deck_name=deck.deck_name,
                    query=session_query,
                    target_seconds=minutes * 60,
                    origin=SessionOrigin.TIME_MACHINE,
                    starting_due_count=deck.card_count,
                    estimated_total=min(expected_cards, deck.card_count),
                    estimated_seconds=estimated_seconds,
                )
                try:
                    self._generated_decks.create(
                        session,
                        feature="time_machine",
                        cards=deck.cards,
                        scope=session_query,
                        metadata={
                            "duration_minutes": minutes,
                            "scope_label": scope_label,
                            "debrief_topic_snapshots": True,
                        },
                    )
                except Exception as error:
                    self._logger.exception(
                        "Unable to create Study by Time history manifest"
                    )
                    self._manager.abandon_saved(session.id)
                    self._discard_unstarted_deck(deck, error)
                    return
                self._target_notified.discard(session.id)
                from aqt.utils import tooltip  # type: ignore[import-not-found]

                tooltip(
                    f"Study by Time · {deck.card_count} cards · {scope_label}",
                    parent=self._mw,
                )
                self._mw.moveToState("review")

            set_current_deck(parent=self._mw, deck_id=deck.deck_id).success(
                selected
            ).failure(
                lambda error: self._discard_unstarted_deck(deck, error)
            ).run_in_background()

        QueryOp(parent=self._mw, op=create, success=created).failure(
            self._start_failed
        ).run_in_background()

    def _retry_start(
        self,
        minutes: int,
        selected_deck_ids: tuple[int, ...],
        scope_label: str,
        session_query: str,
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def collect(collection: Any) -> AllDeckQueueSnapshot:
            fastest = min(
                self._timing.estimate_seconds(bucket) for bucket in TimingBucket
            )
            return collect_selected_deck_queue(
                collection,
                selected_deck_ids,
                fetch_limit=queue_fetch_limit(minutes, fastest),
            )

        def retry(snapshot: AllDeckQueueSnapshot) -> None:
            estimate = self._timing.estimate_session(
                snapshot.buckets, minutes * 60
            )
            self._start_session(
                minutes,
                snapshot,
                estimate.expected_cards,
                estimate.estimated_seconds,
                scope_label=scope_label,
                session_query=session_query,
            )

        QueryOp(parent=self._mw, op=collect, success=retry).failure(
            self._start_failed
        ).run_in_background()

    def _start_failed(self, error: Exception) -> None:
        self._logger.warning("Study by Time start failed: %s", error)
        from aqt.utils import showWarning  # type: ignore[import-not-found]

        showWarning(
            "Vellum could not create the temporary session. No cards "
            "were changed. " + str(error),
            parent=self._mw,
        )

    def _discard_unstarted_deck(self, deck: Any, error: Exception) -> None:
        """Roll back a deck if Anki cannot select it after successful creation."""

        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def inspect(collection: Any) -> bool:
            return bool(collection.decks.is_filtered(deck.deck_id)) and (
                collection.decks.name_if_exists(deck.deck_id) == deck.deck_name
            )

        def checked(owned: bool) -> None:
            if not owned:
                self._start_failed(error)
                return
            from aqt.operations.deck import remove_decks  # type: ignore[import-not-found]

            remove_decks(
                parent=self._mw,
                deck_ids=[deck.deck_id],
                deck_name=deck.deck_name,
            ).success(lambda _changes: self._start_failed(error)).failure(
                self._cleanup_failed
            ).run_in_background()

        QueryOp(parent=self._mw, op=inspect, success=checked).failure(
            self._cleanup_failed
        ).run_in_background()

    def _cleanup_failed(self, error: Exception) -> None:
        self._logger.error("Study by Time cleanup failed: %s", error)
        from aqt.utils import showWarning  # type: ignore[import-not-found]

        showWarning(
            "Vellum could not safely remove its temporary Study by Time deck. "
            "Do not delete similarly named decks manually; reopen Vellum and use "
            "Finish Current Session. " + str(error),
            parent=self._mw,
        )

    def finish_current(self) -> None:
        """Return remaining timed-session cards home and abandon the live session."""

        session = self._manager.current
        if (
            session is None
            or session.origin is not SessionOrigin.TIME_MACHINE
            or session.deck_id is None
            or not session.deck_name
        ):
            from aqt.utils import tooltip  # type: ignore[import-not-found]

            tooltip("No active Study by Time session", parent=self._mw)
            return
        from aqt.utils import askUser  # type: ignore[import-not-found]

        if not askUser(
            "Finish this timed session? Remaining cards will return to "
            "their home decks, and answered-card scheduling will be preserved.",
            parent=self._mw,
        ):
            return
        self._remove_owned_deck(session, abandon=True)

    def _reviewer_ended(self) -> None:
        session = self._manager.current
        if (
            session is None
            or session.origin is not SessionOrigin.TIME_MACHINE
            or session.deck_id is None
            or not session.deck_name
        ):
            return
        self._remove_owned_deck(session, abandon=False, only_if_empty=True)

    def _remove_owned_deck(
        self,
        session: Session,
        *,
        abandon: bool,
        only_if_empty: bool = False,
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        deck_id = int(session.deck_id or 0)
        deck_name = str(session.deck_name or "")
        session_id = session.id

        def inspect(collection: Any) -> bool:
            if not (
                bool(collection.decks.is_filtered(deck_id))
                and collection.decks.name_if_exists(deck_id) == deck_name
            ):
                return False
            if not only_if_empty:
                return True
            escaped = deck_name.replace('"', '\\"')
            return not bool(collection.find_cards(f'deck:"{escaped}"'))

        def checked(owned: bool) -> None:
            if not owned:
                if not only_if_empty:
                    self._start_failed(
                        RuntimeError("saved Study by Time deck identity no longer matches")
                    )
                return
            from aqt.operations.deck import remove_decks  # type: ignore[import-not-found]

            def removed(_changes: Any) -> None:
                current = self._manager.current
                self._generated_decks.mark_removed(
                    session_id,
                    reason="finished" if abandon else "exhausted",
                )
                if abandon:
                    finalized = self._manager.abandon_saved(session_id)
                    self._mw.moveToState("deckBrowser")
                elif (
                    current is not None
                    and current.id == session_id
                    and current.status not in TERMINAL_STATUSES
                ):
                    finalized = self._manager.complete_saved(session_id)
                else:
                    finalized = self._manager.repository.get(session_id)
                self._events.emit(
                    "time_machine_abandoned" if abandon else "time_machine_completed",
                    finalized,
                )
                if finalized is not None:
                    self._events.emit("session_finalized", finalized)

            remove_decks(
                parent=self._mw,
                deck_ids=[deck_id],
                deck_name=deck_name,
            ).success(removed).run_in_background()

        QueryOp(parent=self._mw, op=inspect, success=checked).failure(
            self._cleanup_failed
        ).run_in_background()

    def _target_update(self, session: Session) -> None:
        """Notify only after an answered card, never over a displayed question."""

        if (
            not self._running
            or session.id in self._target_notified
            or not time_target_reached(session)
        ):
            return
        behavior = self._config().time_machine.end_behavior
        if behavior == "no_stop":
            return
        self._target_notified.add(session.id)

        if behavior == "soft_stop":
            from aqt.utils import tooltip  # type: ignore[import-not-found]

            tooltip(
                "Time’s up. Continue at your own pace or finish this session.",
                parent=self._mw,
                period=5000,
            )
            return

        def alert() -> None:
            from aqt.qt import QMessageBox  # type: ignore[import-not-found]

            choice = QMessageBox.question(
                self._mw,
                "Vellum Study by Time",
                "Time’s up, and the current card is complete. Finish this "
                "Vellum session now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                current = self._manager.current
                if current is not None and current.id == session.id:
                    self._remove_owned_deck(current, abandon=True)

        self._mw.progress.single_shot(0, alert, False)
