"""Read-only topic aggregate queries intended for Anki QueryOp execution."""

from __future__ import annotations

from dataclasses import replace
import time
from typing import Any

from ..topics.models import TopicStats
from ..topics.health import classify_topic_health


def quote_search_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def topic_query(raw_tag: str, suffix: str = "") -> str:
    base = f"tag:{quote_search_value(raw_tag)}"
    return f"{base} {suffix}" if suffix else base


def collect_topic_stats(collection: Any, raw_tag: str) -> TopicStats:
    """Gather topic health inputs in one read-only parameterized SQL pass.

    Anki's public search is retained for interactive card selection elsewhere,
    but issuing eight whole-collection searches for every topic stalls the
    backend on large collections. This aggregate reads only IDs, scheduling
    columns, tags, and revlog ratings; it never reads note field content.
    """

    normalized_tag = raw_tag.strip().casefold()
    if not normalized_tag:
        return replace(
            TopicStats(),
            health_state=classify_topic_health(TopicStats()).value,
        )
    exact_needle = f" {normalized_tag} "
    descendant_needle = f" {normalized_tag}::"
    now_seconds = int(time.time())
    failure_cutoff_ms = (now_seconds - 14 * 86400) * 1000
    today = int(collection.sched.today)
    row = collection.db.first(
        """
        WITH matched AS (
            SELECT c.id, c.type, c.queue, c.due, c.ivl
            FROM cards c
            JOIN notes n ON n.id = c.nid
            WHERE instr(lower(n.tags), ?) > 0
               OR instr(lower(n.tags), ?) > 0
        ),
        card_stats AS (
            SELECT
                count(*) AS total_cards,
                coalesce(sum(type = 0), 0) AS new_cards,
                coalesce(sum(type IN (1, 3)), 0) AS learning_cards,
                coalesce(sum(type = 2), 0) AS review_cards,
                coalesce(sum(type = 2 AND ivl >= 21), 0) AS mature_cards,
                coalesce(sum(
                    (queue IN (2, 3) AND due <= ?)
                    OR (queue = 1 AND due <= ?)
                ), 0) AS due_cards
            FROM matched
        ),
        ranked_reviews AS (
            SELECT
                r.cid,
                r.id,
                r.ease,
                row_number() OVER (ORDER BY r.id DESC) AS topic_rank,
                row_number() OVER (
                    PARTITION BY r.cid ORDER BY r.id DESC
                ) AS card_rank
            FROM revlog r
            JOIN matched m ON m.id = r.cid
            WHERE r.ease BETWEEN 1 AND 4
        ),
        review_stats AS (
            SELECT
                coalesce(sum(topic_rank <= 50), 0) AS recent_reviews,
                coalesce(sum(topic_rank <= 50 AND ease <> 1), 0) AS successes,
                coalesce(sum(
                    card_rank = 1 AND id >= ? AND ease = 1
                ), 0) AS recent_failures
            FROM ranked_reviews
        )
        SELECT
            card_stats.total_cards,
            card_stats.new_cards,
            card_stats.learning_cards,
            card_stats.review_cards,
            card_stats.mature_cards,
            card_stats.due_cards,
            review_stats.recent_reviews,
            review_stats.recent_failures,
            review_stats.successes
        FROM card_stats, review_stats
        """,
        exact_needle,
        descendant_needle,
        today,
        now_seconds,
        failure_cutoff_ms,
    )
    values = tuple(row or (0,) * 9)
    (
        total_cards,
        new_cards,
        learning_cards,
        review_cards,
        mature_cards,
        due_cards,
        recent_reviews,
        recent_failures,
        recent_successes,
    ) = (int(value or 0) for value in values)
    retention = (
        recent_successes / recent_reviews
        if recent_reviews
        else None
    )
    stats = TopicStats(
        total_cards=total_cards,
        new_cards=new_cards,
        learning_cards=learning_cards,
        review_cards=review_cards,
        mature_cards=mature_cards,
        due_cards=due_cards,
        recent_reviews=recent_reviews,
        recent_failures=recent_failures,
        retention_estimate=retention,
    )
    return replace(stats, health_state=classify_topic_health(stats).value)
