"""Conservative workflow heuristic for topic attention, not a mastery score."""

from __future__ import annotations

from enum import Enum

from .models import TopicStats


class TopicHealthState(str, Enum):
    STRONG = "Strong"
    STABLE = "Stable"
    FADING = "Fading"
    NEEDS_RECOVERY = "Needs Recovery"
    INSUFFICIENT_DATA = "Insufficient Data"


def classify_topic_health(stats: TopicStats) -> TopicHealthState:
    if stats.total_cards < 5 or stats.recent_reviews < 5:
        return TopicHealthState.INSUFFICIENT_DATA
    retention = stats.retention_estimate
    due_ratio = stats.due_cards / max(1, stats.total_cards)
    failure_ratio = 1.0 - retention if retention is not None else 0.0
    if (
        (retention is not None and retention < 0.75)
        or (stats.recent_failures >= 5 and failure_ratio >= 0.15)
        or (due_ratio >= 0.65 and failure_ratio >= 0.15)
    ):
        return TopicHealthState.NEEDS_RECOVERY
    if (
        (retention is not None and retention < 0.88)
        or (stats.recent_failures >= 2 and failure_ratio >= 0.07)
        or due_ratio >= 0.4
    ):
        return TopicHealthState.FADING
    if stats.recent_failures <= 1 and due_ratio < 0.1 and (
        retention is not None and retention >= 0.95
    ):
        return TopicHealthState.STRONG
    return TopicHealthState.STABLE


def describe_topic_health(stats: TopicStats) -> str:
    """Explain the observable inputs without presenting a mastery score."""

    state = classify_topic_health(stats)
    if state is TopicHealthState.INSUFFICIENT_DATA:
        return (
            f"{stats.total_cards} cards and {stats.recent_reviews} recent rated "
            "reviews; at least 5 of each are required."
        )
    retention = (
        f"{round(stats.retention_estimate * 100)}% retention across the last "
        f"{stats.recent_reviews} rated reviews"
        if stats.retention_estimate is not None
        else "No recent retention sample"
    )
    failures = (
        f"{stats.recent_failures} cards have a latest Again within 14 days"
        if stats.recent_failures
        else "no card has a latest Again within 14 days"
    )
    return (
        f"{retention}; {stats.due_cards} of {stats.total_cards} cards are due; "
        f"{failures}."
    )
