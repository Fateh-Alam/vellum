"""Reviewer hook adapter for persistent normal-study sessions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..anki.hooks import HookRegistry
from ..core.config import VellumConfig
from ..sessions.manager import SessionManager
from ..sessions.generated_decks import GeneratedDeckHistoryRepository
from ..sessions.models import SessionStatus, SessionTopicContext, TERMINAL_STATUSES
from ..topics.service import TopicService
from ..timing.model import TimingModel
from ..timing.models import TimingBucket


CARD_BUCKETS = {
    0: TimingBucket.NEW,
    1: TimingBucket.LEARNING,
    2: TimingBucket.REVIEW,
    3: TimingBucket.RELEARNING,
}


class SessionTrackingModule:
    name = "resume"

    def __init__(
        self,
        manager: SessionManager,
        topics: TopicService,
        timing: TimingModel | None = None,
        mw: Any | None = None,
        config: Callable[[], VellumConfig] | None = None,
        generated_decks: GeneratedDeckHistoryRepository | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._manager = manager
        self._topics = topics
        self._timing = timing
        self._mw = mw
        self._config = config
        self._generated_decks = generated_decks
        self._logger = logger or logging.getLogger("vellum.features.sessions")
        self._hooks = HookRegistry(self._logger)
        self._running = False
        self._owners = 0
        self._shown_buckets: dict[int, TimingBucket] = {}
        self._shown_topics: dict[int, SessionTopicContext] = {}
        self._collection: Any | None = None
        self._checkpoint_timer: Any | None = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._owners += 1
        if self._running:
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        self._hooks.register(gui_hooks.reviewer_did_show_question, self._card_shown)
        self._hooks.register(gui_hooks.reviewer_did_answer_card, self._card_answered)
        self._hooks.register(gui_hooks.reviewer_will_end, self._reviewer_ended)
        self._start_checkpoint_timer()
        self._running = True

    def stop(self) -> None:
        self._owners = max(0, self._owners - 1)
        if not self._running or self._owners:
            return
        self._hooks.clear()
        if self._checkpoint_timer is not None:
            self._checkpoint_timer.stop()
            self._checkpoint_timer.deleteLater()
            self._checkpoint_timer = None
        self._manager.interrupt()
        self._running = False

    def _start_checkpoint_timer(self) -> None:
        if self._mw is None or self._config is None:
            return
        config = self._config().resume
        if not config.enable_checkpoints:
            return
        from aqt.qt import QTimer, qconnect  # type: ignore[import-not-found]

        timer = QTimer(self._mw)
        timer.setInterval(config.checkpoint_seconds * 1000)
        qconnect(timer.timeout, self._manager.checkpoint)
        timer.start()
        self._checkpoint_timer = timer

    def _card_shown(self, card: Any) -> None:
        try:
            self._collection = getattr(card, "col", self._collection)
            topic = self._topics.resolve(int(card.nid), tuple(card.note().tags))
            card_id = int(card.id)
            self._shown_buckets[card_id] = CARD_BUCKETS.get(
                int(getattr(card, "type", 2)), TimingBucket.REVIEW
            )
            topic_context = SessionTopicContext.from_parsed(topic)
            self._shown_topics[card_id] = topic_context
            current = self._manager.current
            if current is None or current.status in TERMINAL_STATUSES or current.status in {
                SessionStatus.INTERRUPTED,
                SessionStatus.PAUSED,
            }:
                deck_id = int(card.current_deck_id())
                try:
                    deck_name = str(card.col.decks.name(deck_id))
                except Exception:
                    deck_name = None
                saved_generated = (
                    self._manager.repository.generated_resumable_for_deck(
                        deck_id, deck_name
                    )
                    if deck_name
                    else None
                )
                if saved_generated is not None:
                    self._manager.resume(saved_generated.id)
                    current = self._manager.current
                else:
                    try:
                        queued = card.col.sched.get_queued_cards(fetch_limit=1)
                        due_count = int(
                            queued.new_count
                            + queued.learning_count
                            + queued.review_count
                        )
                        estimated_seconds = (
                            self._timing.estimate_counts_seconds(
                                {
                                    TimingBucket.NEW: int(queued.new_count),
                                    TimingBucket.LEARNING: int(queued.learning_count),
                                    TimingBucket.REVIEW: int(queued.review_count),
                                }
                            )
                            if self._timing is not None
                            else None
                        )
                    except Exception:
                        due_count = None
                        estimated_seconds = None
                    self._manager.start(
                        deck_id=deck_id,
                        deck_name=deck_name,
                        starting_due_count=due_count,
                        estimated_total=due_count,
                        estimated_seconds=estimated_seconds,
                    )
            try:
                self._manager.show_card(card_id, topic.topic_id)
            except RuntimeError:
                self._manager.start(
                    deck_id=int(card.current_deck_id()),
                    deck_name=None,
                )
                self._manager.show_card(card_id, topic.topic_id)
        except Exception:
            self._logger.exception("Unable to checkpoint shown card")

    def _card_answered(self, _reviewer: Any, card: Any, ease: int) -> None:
        try:
            card_id = int(card.id)
            topic = self._shown_topics.pop(card_id, SessionTopicContext())
            try:
                duration_ms = int(card.time_taken())
            except Exception:
                duration_ms = None
            current = self._manager.current
            if (
                self._timing is not None
                and duration_ms is not None
                and current is not None
            ):
                bucket = self._shown_buckets.pop(card_id, TimingBucket.REVIEW)
                self._record_timing_after_transition(
                    bucket,
                    duration_ms,
                    current.id,
                )
            self._manager.answer_card(
                card_id, int(ease), duration_ms, topic
            )
            self._record_generated_deck_answer_after_transition(
                current.id,
                card_id,
                int(ease),
                duration_ms,
                self._manager.last_reviewed_at_ms,
            )
        except Exception:
            self._logger.exception("Unable to checkpoint answered card")

    def _record_timing_after_transition(
        self,
        bucket: TimingBucket,
        duration_ms: int,
        session_id: str,
    ) -> None:
        """Keep robust timing aggregation out of Anki's next-card critical path."""

        if self._timing is None:
            return

        def record() -> None:
            try:
                self._timing.record(bucket, duration_ms, session_id)
            except Exception:
                self._logger.exception("Unable to persist deferred timing sample")

        if self._mw is not None:
            self._mw.progress.single_shot(25, record, False)
        else:
            record()

    def _record_generated_deck_answer_after_transition(
        self,
        session_id: str,
        card_id: int,
        rating: int,
        duration_ms: int | None,
        answered_at: int,
    ) -> None:
        if self._generated_decks is None:
            return

        def record() -> None:
            try:
                self._generated_decks.record_answer(
                    session_id,
                    card_id=card_id,
                    answered_at=answered_at,
                    rating=rating,
                    duration_ms=duration_ms,
                )
            except Exception:
                self._logger.exception("Unable to update generated deck history")

        if self._mw is not None:
            self._mw.progress.single_shot(25, record, False)
        else:
            record()

    def _reviewer_ended(self) -> None:
        current = self._manager.current
        if current is None or current.status in TERMINAL_STATUSES:
            return
        # Generated-deck features own their exact filtered-deck inspection and
        # cleanup. They first mark an early exit interrupted, then complete the
        # same saved session only after the owned deck is verified empty and
        # removed.
        from ..sessions.models import SessionOrigin

        if current.origin in {
            SessionOrigin.RECOVERY,
            SessionOrigin.TIME_MACHINE,
            SessionOrigin.STUDY_BUILDER,
        }:
            self._manager.interrupt()
            return
        try:
            collection = self._collection
            if collection is None:
                self._manager.interrupt()
                return
            queued = collection.sched.get_queued_cards(fetch_limit=1)
            remaining = int(
                queued.new_count + queued.learning_count + queued.review_count
            )
            if remaining == 0:
                self._manager.complete()
            else:
                self._manager.interrupt()
        except Exception:
            self._logger.exception("Unable to distinguish completed reviewer queue")
            self._manager.interrupt()
