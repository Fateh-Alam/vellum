"""Explicit, persisted session lifecycle with inactivity splitting."""

from __future__ import annotations

from dataclasses import replace
import time
import uuid
from collections.abc import Callable

from ..core.events import EventBus
from .models import (
    Session,
    SessionOrigin,
    SessionStatus,
    SessionTopicContext,
    TERMINAL_STATUSES,
)
from .repository import SessionRepository


class SessionManager:
    def __init__(
        self,
        repository: SessionRepository,
        events: EventBus | None = None,
        clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        inactivity_seconds: int = 1800,
    ) -> None:
        self.repository = repository
        self.events = events
        self.clock = clock
        self.id_factory = id_factory
        self.inactivity_seconds = inactivity_seconds
        self.current: Session | None = None
        self._last_reviewed_at_ms = 0

    @property
    def last_reviewed_at_ms(self) -> int:
        return self._last_reviewed_at_ms

    def start(
        self,
        *,
        deck_id: int | None = None,
        deck_name: str | None = None,
        query: str | None = None,
        target_seconds: int | None = None,
        origin: SessionOrigin = SessionOrigin.NORMAL,
        starting_due_count: int | None = None,
        estimated_total: int | None = None,
        estimated_seconds: float | None = None,
    ) -> Session:
        now = int(self.clock())
        if self.current and self.current.status not in TERMINAL_STATUSES:
            self.interrupt()
        session = Session(
            id=self.id_factory(),
            started_at=now,
            last_active_at=now,
            status=SessionStatus.STARTED,
            deck_id=deck_id,
            deck_name=deck_name,
            query=query,
            target_seconds=target_seconds,
            origin=origin,
            starting_due_count=starting_due_count,
            estimated_total=estimated_total,
            estimated_seconds=estimated_seconds,
        )
        self.repository.save(session)
        self.current = session
        self._emit("session_started", session)
        return session

    def show_card(self, card_id: int, topic_id: str | None) -> Session:
        session = self._require_current()
        now = int(self.clock())
        if now - session.last_active_at > self.inactivity_seconds:
            self.interrupt()
            raise RuntimeError("Session interrupted after inactivity")
        topics = list(session.recent_topic_ids)
        if topic_id and (not topics or topics[-1] != topic_id):
            topics.append(topic_id)
            topics = topics[-10:]
        status = (
            SessionStatus.ACTIVE
            if session.status in {SessionStatus.STARTED, SessionStatus.RESUMED}
            else session.status
        )
        session = replace(
            session,
            status=status,
            last_active_at=now,
            last_card_id=card_id,
            last_topic_id=topic_id,
            recent_topic_ids=tuple(topics),
        )
        self.repository.save(session)
        self.current = session
        self._emit("session_updated", session)
        return session

    def answer_card(
        self,
        card_id: int,
        rating: int,
        duration_ms: int | None,
        topic: SessionTopicContext | str | None,
    ) -> Session:
        session = self._require_current()
        clock_value = self.clock()
        now = int(clock_value)
        reviewed_at_ms = max(
            self._last_reviewed_at_ms + 1, int(clock_value * 1000)
        )
        self._last_reviewed_at_ms = reviewed_at_ms
        duration = duration_ms if duration_ms is not None and 250 <= duration_ms <= 120_000 else None
        topic_context = (
            topic if isinstance(topic, SessionTopicContext)
            else SessionTopicContext(topic_id=topic)
        )
        session = replace(
            session,
            status=SessionStatus.ACTIVE,
            last_active_at=now,
            last_card_id=card_id,
            last_topic_id=topic_context.topic_id,
            reviewed_count=session.reviewed_count + 1,
        )
        self.repository.record_answer(
            session,
            card_id=card_id,
            reviewed_at=reviewed_at_ms,
            rating=rating,
            duration_ms=duration,
            topic=topic_context,
        )
        self.current = session
        self._emit("session_updated", session)
        self._emit("session_card_answered", session)
        return session

    def interrupt(self) -> Session | None:
        return self._transition(SessionStatus.INTERRUPTED, "session_interrupted")

    def complete(self) -> Session | None:
        return self._transition(SessionStatus.COMPLETED, "session_completed")

    def abandon(self) -> Session | None:
        return self._transition(SessionStatus.ABANDONED, "session_abandoned")

    def abandon_saved(self, session_id: str) -> Session:
        session = self.repository.get(session_id)
        if session is None or session.status in TERMINAL_STATUSES:
            raise ValueError("Session is not abandonable")
        session = session.transition(SessionStatus.ABANDONED, int(self.clock()))
        self.repository.save(session)
        if self.current and self.current.id == session_id:
            self.current = session
        self._emit("session_abandoned", session)
        return session

    def complete_saved(self, session_id: str) -> Session:
        session = self.repository.get(session_id)
        if session is None or session.status in TERMINAL_STATUSES:
            raise ValueError("Session is not completable")
        session = session.transition(SessionStatus.COMPLETED, int(self.clock()))
        self.repository.save(session)
        if self.current and self.current.id == session_id:
            self.current = session
        self._emit("session_completed", session)
        return session

    def resume(self, session_id: str) -> Session:
        session = self.repository.get(session_id)
        if session is None or session.status in TERMINAL_STATUSES:
            raise ValueError("Session is not resumable")
        session = session.transition(SessionStatus.RESUMED, int(self.clock()))
        self.repository.save(session)
        self.current = session
        self._emit("session_resumed", session)
        return session

    def checkpoint(self) -> Session | None:
        """Flush the current in-memory session without manufacturing activity."""

        session = self.current
        if session is None or session.status in TERMINAL_STATUSES:
            return session
        self.repository.save(session)
        self._emit("session_checkpointed", session)
        return session

    def _transition(self, status: SessionStatus, event: str) -> Session | None:
        if self.current is None or self.current.status in TERMINAL_STATUSES:
            return self.current
        session = self.current.transition(status, int(self.clock()))
        self.repository.save(session)
        self.current = session
        self._emit(event, session)
        return session

    def _require_current(self) -> Session:
        if self.current is None or self.current.status in TERMINAL_STATUSES:
            raise RuntimeError("No active Vellum session")
        return self.current

    def _emit(self, event: str, session: Session) -> None:
        if self.events is not None:
            self.events.emit(event, session)
