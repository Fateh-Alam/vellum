"""Session state machine models."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class SessionStatus(str, Enum):
    STARTED = "started"
    ACTIVE = "active"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    RESUMED = "resumed"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SessionOrigin(str, Enum):
    NORMAL = "normal"
    TIME_MACHINE = "time_machine"
    RECOVERY = "recovery"
    STUDY_BUILDER = "study_builder"
    RESUMED = "resumed"


TERMINAL_STATUSES = frozenset({SessionStatus.COMPLETED, SessionStatus.ABANDONED})


@dataclass(frozen=True)
class Session:
    id: str
    started_at: int
    last_active_at: int
    status: SessionStatus
    deck_id: int | None = None
    deck_name: str | None = None
    query: str | None = None
    target_seconds: int | None = None
    origin: SessionOrigin = SessionOrigin.NORMAL
    last_card_id: int | None = None
    last_topic_id: str | None = None
    reviewed_count: int = 0
    starting_due_count: int | None = None
    estimated_total: int | None = None
    estimated_seconds: float | None = None
    ended_at: int | None = None
    recent_topic_ids: tuple[str, ...] = ()

    def transition(self, status: SessionStatus, now: int) -> "Session":
        if self.status in TERMINAL_STATUSES:
            raise ValueError(f"Cannot transition terminal session {self.id}")
        ended = now if status in TERMINAL_STATUSES else None
        return replace(
            self,
            status=status,
            last_active_at=now,
            ended_at=ended,
            origin=self.origin,
        )


@dataclass(frozen=True)
class SessionTopicContext:
    topic_id: str | None = None
    label: str | None = None
    path: tuple[str, ...] = ()
    raw_topic_tag: str | None = None

    @classmethod
    def from_parsed(cls, parsed: Any) -> "SessionTopicContext":
        path = tuple(getattr(parsed, "path", ()) or ())
        return cls(
            topic_id=getattr(parsed, "topic_id", None),
            label=path[-1] if path else None,
            path=path,
            raw_topic_tag=getattr(parsed, "raw_tag", None) or None,
        )
