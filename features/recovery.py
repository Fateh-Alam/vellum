"""Independent current-card to temporary topic-recovery workflow."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from ..anki.hooks import HookRegistry
from ..anki.recovery import RecoveryQueryResult, collect_recovery_candidates
from ..anki.shortcuts import append_state_shortcut
from ..core.config import RecoveryConfig, VellumConfig
from ..core.events import EventBus
from ..recovery.models import RecoveryPlan
from ..recovery.planner import build_recovery_plan
from ..sessions.manager import SessionManager
from ..sessions.generated_decks import (
    GeneratedDeckCard,
    GeneratedDeckHistoryRepository,
    collect_generated_deck_cards,
)
from ..sessions.models import SessionOrigin
from ..topics.models import ParsedTopicPath
from ..topics.service import TopicService
from ..timing.model import TimingModel
from ..timing.models import TimingBucket
from ..ui.recovery import (
    RecoverySelection,
    confirm_recovery_plan,
    open_native_filtered_deck,
    show_recovery_dialog,
)
from .session_tracking import SessionTrackingModule


TOPIC_ID = re.compile(r"^[0-9a-f]{40}$")
RECOVER_MESSAGE = "vellum:recover:"


class RecoveryModule:
    name = "recovery"

    def __init__(
        self,
        mw: Any,
        topics: TopicService,
        manager: SessionManager,
        tracking: SessionTrackingModule,
        config: Callable[[], VellumConfig],
        events: EventBus,
        generated_decks: GeneratedDeckHistoryRepository,
        timing: TimingModel,
        logger: logging.Logger | None = None,
    ) -> None:
        self._mw = mw
        self._topics = topics
        self._manager = manager
        self._tracking = tracking
        self._config = config
        self._events = events
        self._generated_decks = generated_decks
        self._timing = timing
        self._logger = logger or logging.getLogger("vellum.features.recovery")
        self._hooks = HookRegistry(self._logger)
        self._action: Any | None = None
        self._running = False
        self._last_level_offset = 0
        self._unsubscribe: Callable[[], None] | None = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        self._tracking.start()
        self._install_action()
        self._configure_shortcut()
        self._action.setEnabled(True)
        self._hooks.register(
            gui_hooks.reviewer_will_show_context_menu, self._context_menu
        )
        self._hooks.register(
            gui_hooks.webview_did_receive_js_message, self._receive_message
        )
        self._hooks.register(gui_hooks.reviewer_will_end, self._reviewer_ended)
        self._hooks.register(
            gui_hooks.state_shortcuts_will_change, self._state_shortcuts
        )
        self._unsubscribe = self._events.subscribe(
            "topic_open_requested",
            lambda topic_id: self.open(requested_topic_id=topic_id),
        )
        self._running = True
        self._logger.info("Topic Recovery enabled")

    def stop(self) -> None:
        if not self._running:
            return
        self._hooks.clear()
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._tracking.stop()
        if self._action is not None:
            self._action.setEnabled(False)
            self._action.setShortcut("")
        self._running = False

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Recover Current Topic…", self._mw)
        qconnect(self._action.triggered, lambda: self.open())
        self._mw.addAction(self._action)

    def _configure_shortcut(self) -> None:
        self._action.setShortcut("")

    def _state_shortcuts(self, state: str, shortcuts: list[tuple[Any, ...]]) -> None:
        if state != "review":
            return
        full_config = self._config()
        config = full_config.recovery
        append_state_shortcut(
            shortcuts,
            config.shortcut,
            self.open,
            enabled=full_config.general.keyboard_shortcuts
            and config.shortcut_enabled,
            logger=self._logger,
            feature_name="Recovery",
            owner=self._mw,
        )

    def _context_menu(self, reviewer: Any, menu: Any) -> None:
        action = menu.addAction("Recover this topic with Vellum…")
        action.triggered.connect(lambda: self.open(card=getattr(reviewer, "card", None)))

    def _receive_message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ != "Reviewer" or not message.startswith(
            RECOVER_MESSAGE
        ):
            return handled
        requested = message[len(RECOVER_MESSAGE) :]
        if TOPIC_ID.fullmatch(requested):
            self.open(card=getattr(context, "card", None), requested_topic_id=requested)
        return (True, None)

    def open(
        self, card: Any | None = None, requested_topic_id: str | None = None
    ) -> None:
        if not self._running:
            return
        saved = self._manager.repository.latest_generated_resumable()
        if saved is not None:
            self._warn(
                "A Vellum-generated session is already unfinished. Resume, "
                "finish, or abandon it before creating another filtered deck."
            )
            return
        card = card or getattr(getattr(self._mw, "reviewer", None), "card", None)
        if card is None:
            self._warn("Open a review card before starting Topic Recovery.")
            return
        try:
            note = card.note()
            tags = tuple(str(tag) for tag in getattr(note, "tags", ()))
            parsed = self._topics.resolve(int(card.nid), tags)
        except Exception:
            self._logger.exception("Unable to resolve current Recovery topic")
            self._warn("Vellum could not read the current card's topic tags.")
            return
        if not parsed.found or len(parsed.raw_prefixes) != len(parsed.path):
            self._warn("No recoverable hierarchical topic was found on this card.")
            return

        config = self._config().recovery
        default_index = self._requested_level(parsed, requested_topic_id, config)
        selection = show_recovery_dialog(
            self._mw,
            parsed.path,
            default_level_index=default_index,
            config=config,
        )
        if selection is None:
            return
        self._last_level_offset = len(parsed.path) - 1 - selection.level_index
        self._load_plan(parsed, int(card.id), selection)

    def open_topic(
        self,
        *,
        topic_id: str,
        topic_label: str,
        topic_path: tuple[str, ...],
        raw_topic_tag: str,
    ) -> None:
        """Start a leaf-level Recovery from a stored Debrief topic snapshot."""

        if not self._running or not topic_id or not raw_topic_tag:
            self._warn("This historical topic is not recoverable.")
            return
        saved = self._manager.repository.latest_generated_resumable()
        if saved is not None:
            self._warn(
                "A Vellum-generated session is already unfinished. Resume, "
                "finish, or abandon it before creating another filtered deck."
            )
            return
        label = topic_label.strip() or (topic_path[-1] if topic_path else "Topic")
        parsed = ParsedTopicPath(
            raw_tag=raw_topic_tag,
            source_root=None,
            path=(label,),
            canonical_path=(label.casefold(),),
            topic_id=topic_id,
            raw_prefixes=(raw_topic_tag,),
        )
        selection = show_recovery_dialog(
            self._mw,
            parsed.path,
            default_level_index=0,
            config=self._config().recovery,
        )
        if selection is not None:
            self._load_plan(parsed, 0, selection)

    def _requested_level(
        self,
        parsed: ParsedTopicPath,
        requested_topic_id: str | None,
        config: RecoveryConfig,
    ) -> int:
        ids = (*parsed.ancestor_topic_ids, parsed.topic_id)
        if requested_topic_id in ids:
            return ids.index(requested_topic_id)
        if config.default_level == "remember_last":
            return max(0, len(parsed.path) - 1 - self._last_level_offset)
        return len(parsed.path) - 1

    def _load_plan(
        self,
        parsed: ParsedTopicPath,
        current_card_id: int,
        selection: RecoverySelection,
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        prefix = parsed.raw_prefixes[selection.level_index]
        config = self._config().recovery

        def gather(collection: Any) -> RecoveryQueryResult:
            return collect_recovery_candidates(
                collection,
                prefix,
                current_card_id=current_card_id,
                recent_failure_days=config.recent_failure_days,
            )

        def success(result: RecoveryQueryResult) -> None:
            plan = build_recovery_plan(
                topic_label=parsed.path[selection.level_index],
                raw_tag_prefix=prefix,
                mode=selection.mode,
                candidates=result.candidates,
                config=config,
                custom=selection.custom,
            )
            self._logger.debug(
                "Recovery plan topic=%s mode=%s selected=%d available=%d top=%s",
                plan.topic_label,
                plan.mode.value,
                len(plan.cards),
                plan.available_count,
                [
                    "card_id=%d score=%g reasons=%s"
                    % (
                        item.candidate.card_id,
                        item.score,
                        "; ".join(item.reasons[:3]),
                    )
                    for item in plan.cards[:12]
                ],
            )
            if not plan.cards:
                self._warn(
                    "No eligible cards matched this Recovery level. Suspended, buried, "
                    "and already-filtered cards cannot be pulled into a new filtered deck."
                )
                return
            if config.ask_before_create and not confirm_recovery_plan(
                self._mw, plan, excluded_count=result.excluded_count
            ):
                return
            self._open_filtered_deck(plan, parsed, selection.level_index)

        QueryOp(parent=self._mw, op=gather, success=success).failure(
            self._query_failed
        ).run_in_background()

    def _open_filtered_deck(
        self, plan: RecoveryPlan, parsed: ParsedTopicPath, level_index: int
    ) -> None:
        config = self._config().recovery
        deck_name = config.deck_name_pattern.replace("{topic}", plan.topic_label)
        open_native_filtered_deck(
            self._mw,
            plan=plan,
            deck_name=deck_name,
            on_created=lambda deck_id, actual_name: self._start(
                deck_id, actual_name, plan, parsed, level_index
            ),
        )

    def _start(
        self,
        deck_id: int,
        deck_name: str,
        plan: RecoveryPlan,
        parsed: ParsedTopicPath,
        level_index: int,
    ) -> None:
        topic_ids = (*parsed.ancestor_topic_ids, parsed.topic_id)
        topic_id = topic_ids[level_index]
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def capture(collection: Any) -> tuple[GeneratedDeckCard, ...]:
            if not (
                bool(collection.decks.is_filtered(deck_id))
                and collection.decks.name_if_exists(deck_id) == deck_name
            ):
                raise RuntimeError("Recovery deck identity changed before start")
            actual_ids = tuple(
                int(row[0])
                for row in collection.db.all(
                    "select id from cards where did = ? order by due, id", deck_id
                )
            )
            buckets = {
                item.candidate.card_id: item.candidate.state for item in plan.cards
            }
            cards = collect_generated_deck_cards(
                collection,
                deck_id,
                actual_ids,
                buckets=buckets,
            )
            if not cards:
                raise RuntimeError("The Recovery deck contains no cards")
            return cards

        def captured(cards: tuple[GeneratedDeckCard, ...]) -> None:
            self._select_start(deck_id, deck_name, plan, topic_id, cards)

        QueryOp(parent=self._mw, op=capture, success=captured).failure(
            lambda error: self._discard_unstarted_deck(deck_id, deck_name, error)
        ).run_in_background()

    def _select_start(
        self,
        deck_id: int,
        deck_name: str,
        plan: RecoveryPlan,
        topic_id: str,
        cards: tuple[GeneratedDeckCard, ...],
    ) -> None:
        from aqt.operations.deck import set_current_deck  # type: ignore[import-not-found]

        query = "cid:" + ",".join(str(card.card_id) for card in cards)
        bucket_names = {
            "new": TimingBucket.NEW,
            "learning": TimingBucket.LEARNING,
            "review": TimingBucket.REVIEW,
            "relearning": TimingBucket.RELEARNING,
        }
        counts = {bucket: 0 for bucket in TimingBucket}
        for card in cards:
            counts[bucket_names.get(card.bucket or "review", TimingBucket.REVIEW)] += 1
        estimated_seconds = self._timing.estimate_counts_seconds(counts)

        def selected(_changes: Any) -> None:
            session = self._manager.start(
                deck_id=deck_id,
                deck_name=deck_name,
                query=query,
                origin=SessionOrigin.RECOVERY,
                starting_due_count=len(cards),
                estimated_total=len(cards),
                estimated_seconds=estimated_seconds,
            )
            try:
                self._generated_decks.create(
                    session,
                    feature="recovery",
                    cards=cards,
                    scope=plan.raw_tag_prefix,
                    metadata={
                        "topic_label": plan.topic_label,
                        "topic_id": topic_id,
                        "mode": plan.mode.value,
                        "preview_card_count": len(plan.cards),
                        "debrief_topic_snapshots": True,
                    },
                )
            except Exception as error:
                self._logger.exception("Unable to create Recovery history manifest")
                self._manager.abandon_saved(session.id)
                self._discard_unstarted_deck(deck_id, deck_name, error)
                return
            self._events.emit("recovery_started", plan, topic_id)
            from aqt.utils import tooltip  # type: ignore[import-not-found]

            tooltip(
                f"Recovery session created · {len(cards)} cards",
                parent=self._mw,
            )
            self._mw.moveToState("review")

        set_current_deck(parent=self._mw, deck_id=deck_id).success(
            selected
        ).failure(
            lambda error: self._discard_unstarted_deck(deck_id, deck_name, error)
        ).run_in_background()

    def _discard_unstarted_deck(
        self, deck_id: int, deck_name: str, error: Exception
    ) -> None:
        """Remove only the exact Recovery deck when start/history setup fails."""

        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def inspect(collection: Any) -> bool:
            return bool(collection.decks.is_filtered(deck_id)) and (
                collection.decks.name_if_exists(deck_id) == deck_name
            )

        def checked(owned: bool) -> None:
            if not owned:
                self._query_failed(error)
                return
            from aqt.operations.deck import remove_decks  # type: ignore[import-not-found]

            remove_decks(
                parent=self._mw,
                deck_ids=[deck_id],
                deck_name=deck_name,
            ).success(lambda _changes: self._query_failed(error)).failure(
                self._query_failed
            ).run_in_background()

        QueryOp(parent=self._mw, op=inspect, success=checked).failure(
            self._query_failed
        ).run_in_background()

    def _query_failed(self, error: Exception) -> None:
        self._logger.error(
            "Recovery candidate query failed",
            exc_info=(type(error), error, error.__traceback__),
        )
        self._warn(f"Recovery could not build a safe card set: {error}")

    def finish_current(self) -> None:
        """Cancel an active Recovery and return every remaining card home."""

        session = self._manager.current
        if (
            session is None
            or session.origin is not SessionOrigin.RECOVERY
            or session.deck_id is None
            or not session.deck_name
        ):
            from aqt.utils import tooltip  # type: ignore[import-not-found]

            tooltip("No active Recovery session", parent=self._mw)
            return
        from aqt.utils import askUser  # type: ignore[import-not-found]

        if not askUser(
            "Finish this Recovery session? Remaining cards will return to their "
            "home decks, and answered-card scheduling will be preserved.",
            parent=self._mw,
        ):
            return
        session_id = session.id
        deck_id = session.deck_id
        deck_name = session.deck_name
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def owns_deck(collection: Any) -> bool:
            return bool(collection.decks.is_filtered(deck_id)) and (
                collection.decks.name_if_exists(deck_id) == deck_name
            )

        def checked(owned: bool) -> None:
            if not owned:
                self._warn(
                    "Vellum refused to remove this deck because its saved identity "
                    "no longer matches the active Recovery session."
                )
                return
            from aqt.operations.deck import remove_decks  # type: ignore[import-not-found]

            def removed(_changes: Any) -> None:
                self._generated_decks.mark_removed(
                    session_id, reason="finished"
                )
                abandoned = self._manager.abandon_saved(session_id)
                self._events.emit("recovery_abandoned", abandoned)
                self._events.emit("session_finalized", abandoned)
                self._mw.moveToState("deckBrowser")

            remove_decks(
                parent=self._mw,
                deck_ids=[deck_id],
                deck_name=deck_name,
            ).success(removed).run_in_background()

        QueryOp(parent=self._mw, op=owns_deck, success=checked).failure(
            lambda error: self._query_failed(error)
        ).run_in_background()

    def _reviewer_ended(self) -> None:
        """Remove only a Vellum-created filtered deck after it is empty."""

        session = self._manager.current
        if (
            session is None
            or session.origin is not SessionOrigin.RECOVERY
            or session.deck_id is None
            or not session.deck_name
        ):
            return
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        deck_id = session.deck_id
        deck_name = session.deck_name
        session_id = session.id

        def inspect(collection: Any) -> bool:
            try:
                return (
                    bool(collection.decks.is_filtered(deck_id))
                    and collection.decks.name_if_exists(deck_id) == deck_name
                    and not bool(
                    collection.find_cards(
                        'deck:"' + deck_name.replace('"', '\\"') + '"'
                    )
                    )
                )
            except Exception:
                return False

        def cleanup(empty_filtered: bool) -> None:
            if not empty_filtered:
                return
            from aqt.operations.deck import remove_decks  # type: ignore[import-not-found]

            def removed(_changes: Any) -> None:
                self._generated_decks.mark_removed(
                    session_id, reason="exhausted"
                )
                completed = self._manager.complete_saved(session_id)
                self._events.emit("recovery_completed", completed)
                self._events.emit("session_finalized", completed)

            remove_decks(
                parent=self._mw,
                deck_ids=[deck_id],
                deck_name=deck_name,
            ).success(removed).run_in_background()

        QueryOp(parent=self._mw, op=inspect, success=cleanup).run_in_background()

    def _warn(self, message: str) -> None:
        from aqt.utils import showWarning  # type: ignore[import-not-found]

        showWarning(message, parent=self._mw)
