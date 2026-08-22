"""Resume assessment that never promises an unsafe historical queue."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
from collections.abc import Callable

from .models import Session


class ResumeMode(str, Enum):
    EXACT = "exact"
    CONTEXT = "context"


@dataclass(frozen=True)
class ResumeAssessment:
    session: Session
    mode: ResumeMode
    age_seconds: int
    stale: bool
    expected_remaining: int | None
    current_due: int | None
    newly_due: int
    explanation: str


class ResumePlanner:
    def __init__(
        self,
        stale_after_days: int = 7,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.stale_after_days = stale_after_days
        self.clock = clock

    def assess(self, session: Session, current_due: int | None) -> ResumeAssessment:
        age = max(0, int(self.clock()) - session.last_active_at)
        stale = age > self.stale_after_days * 86_400
        remaining = (
            max(0, session.starting_due_count - session.reviewed_count)
            if session.starting_due_count is not None
            else None
        )
        newly_due = (
            max(0, current_due - remaining)
            if current_due is not None and remaining is not None
            else 0
        )

        if stale:
            mode = ResumeMode.CONTEXT
            explanation = "The deck may have changed since this session."
        elif session.deck_id is None:
            mode = ResumeMode.CONTEXT
            explanation = "The original deck is unavailable; only study context is safe."
        elif remaining is None or current_due is None:
            mode = ResumeMode.CONTEXT
            explanation = "The original queue size cannot be verified."
        elif current_due != remaining:
            mode = ResumeMode.CONTEXT
            explanation = "Anki's current due queue differs from the saved checkpoint."
        else:
            mode = ResumeMode.EXACT
            explanation = "The saved deck and due count still match."

        return ResumeAssessment(
            session=session,
            mode=mode,
            age_seconds=age,
            stale=stale,
            expected_remaining=remaining,
            current_due=current_due,
            newly_due=newly_due,
            explanation=explanation,
        )
