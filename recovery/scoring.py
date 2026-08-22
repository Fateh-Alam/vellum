"""Transparent V1 Recovery score; every contribution is user-explainable."""

from __future__ import annotations

from .models import RecoveryCandidate, ScoredRecoveryCard


def score_candidate(
    candidate: RecoveryCandidate, *, prioritize_difficult: bool = False
) -> ScoredRecoveryCard:
    contributions: list[tuple[float, str]] = []

    if candidate.state == "relearning":
        contributions.append((2.0, "currently relearning"))

    if candidate.recent_again_count:
        points = min(9.0, candidate.recent_again_count * 3.0)
        contributions.append(
            (points, f"{candidate.recent_again_count} recent Again answer(s)")
        )

    if candidate.lapses:
        points = min(4.0, candidate.lapses * 0.8)
        contributions.append((points, f"{candidate.lapses} recorded lapse(s)"))

    if candidate.stability is not None:
        if candidate.stability < 1:
            contributions.append((3.0, "very low memory stability"))
        elif candidate.stability < 7:
            contributions.append((2.25, "low memory stability"))
        elif candidate.stability < 21:
            contributions.append((1.25, "fading memory stability"))

    if (
        candidate.recent_review_count >= 2
        and candidate.recent_success_rate is not None
        and candidate.recent_success_rate < 0.85
    ):
        points = min(4.0, (0.85 - candidate.recent_success_rate) * 5.0)
        contributions.append(
            (points, f"{candidate.recent_success_rate:.0%} recent retention")
        )

    if candidate.overdue_days > 0:
        points = min(3.0, candidate.overdue_days / 7.0)
        contributions.append((points, f"{candidate.overdue_days} day(s) overdue"))

    if (
        prioritize_difficult
        and candidate.difficulty is not None
        and candidate.difficulty > 7
    ):
        points = min(2.0, (candidate.difficulty - 7) * 0.5)
        contributions.append((points, "high FSRS difficulty"))

    contributions.sort(key=lambda item: (-item[0], item[1]))
    return ScoredRecoveryCard(
        candidate=candidate,
        score=round(sum(points for points, _ in contributions), 2),
        reasons=tuple(f"+{points:g} {reason}" for points, reason in contributions),
    )
