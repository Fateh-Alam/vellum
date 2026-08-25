#!/usr/bin/env python3
"""Repeatable local algorithm/peristence performance smoke checks."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from vellum.core.config import RecoveryConfig, TopicParsingConfig  # noqa: E402
from vellum.builder.catalog import build_catalog  # noqa: E402
from vellum.builder.models import BuilderDefinition, StatePreset  # noqa: E402
from vellum.builder.query import compile_builder_query  # noqa: E402
from vellum.core.db import Database  # noqa: E402
from vellum.recovery.models import RecoveryCandidate, RecoveryMode  # noqa: E402
from vellum.recovery.planner import build_recovery_plan  # noqa: E402
from vellum.timing.model import TimingModel  # noqa: E402
from vellum.timing.models import TimingBucket  # noqa: E402
from vellum.timing.repository import TimingRepository  # noqa: E402
from vellum.topics.cache import TopicPathCache  # noqa: E402
from vellum.topics.parser import TopicParser  # noqa: E402
from vellum.topics.service import TopicService  # noqa: E402


def milliseconds(start: float) -> float:
    return round((perf_counter() - start) * 1000, 3)


def candidate(index: int) -> RecoveryCandidate:
    return RecoveryCandidate(
        card_id=index + 1,
        note_id=index + 1,
        state="review",
        lapses=index % 6,
        stability=float(1 + index % 30),
        difficulty=float(1 + index % 10),
        interval_days=1 + index % 120,
        overdue_days=index % 40,
        recent_again_count=1 if index % 9 == 0 else 0,
        recent_review_count=5,
        recent_success_rate=0.8 if index % 9 == 0 else 1.0,
        added_order=index,
        cloze_index=index % 4,
        is_current=index == 0,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vellum-performance-") as temp_dir:
        database_path = Path(temp_dir) / "vellum.sqlite3"
        start = perf_counter()
        database = Database(database_path)
        database.migrate()
        migration_ms = milliseconds(start)
        try:
            parser = TopicParser(TopicParsingConfig())
            topics = TopicService(parser, TopicPathCache(database))
            tags = ("#AK_Step1_v12::#FirstAid::Renal::Pathology::ADTKD",)

            start = perf_counter()
            first = topics.resolve(1, tags)
            topic_cold_ms = milliseconds(start)
            assert first.found

            start = perf_counter()
            for _ in range(10_000):
                assert topics.resolve(1, tags).topic_id == first.topic_id
            topic_hot_10k_ms = milliseconds(start)

            timing = TimingModel(
                TimingRepository(database),
                {
                    TimingBucket.NEW: 20.0,
                    TimingBucket.LEARNING: 12.0,
                    TimingBucket.REVIEW: 7.0,
                    TimingBucket.RELEARNING: 10.0,
                },
            )
            start = perf_counter()
            seconds = timing.estimate_counts_seconds(
                {
                    TimingBucket.NEW: 10_000,
                    TimingBucket.LEARNING: 10_000,
                    TimingBucket.REVIEW: 70_000,
                    TimingBucket.RELEARNING: 10_000,
                }
            )
            timing_100k_ms = milliseconds(start)
            assert seconds > 0

            maximum = 100_000
            candidates = [candidate(index) for index in range(maximum)]
            recovery_ms: dict[str, float] = {}
            for size in (1_000, 10_000, 30_000, 100_000):
                start = perf_counter()
                plan = build_recovery_plan(
                    topic_label="Performance Fixture",
                    raw_tag_prefix="Performance::Fixture",
                    mode=RecoveryMode.STANDARD,
                    candidates=candidates[:size],
                    config=RecoveryConfig(max_standard=30),
                )
                recovery_ms[str(size)] = milliseconds(start)
                assert plan.cards

            anking_tags = tuple(
                "#AK_Step1_v12::#FirstAid::14_Renal::Pathology::Chapter_"
                f"{index // 100:03d}::Card_Group_{index:05d}"
                for index in range(50_000)
            )
            start = perf_counter()
            builder_catalog = build_catalog(
                deck_names=("AnKing", "Medicine::Renal"),
                tags=anking_tags,
                note_types=("AnKingOverhaul", "Cloze"),
                card_types=("Card 1", "Cloze"),
            )
            builder_catalog_50k_tags_ms = milliseconds(start)
            assert builder_catalog.has_anking
            assert "#AK_Step1_v12::#FirstAid::14_Renal" in {
                facet.value for facet in builder_catalog.anking
            }
            search_samples_ms: list[float] = []
            for _iteration in range(250):
                for query in ("r", "renal", "first aid renal", "chapter 123"):
                    start = perf_counter()
                    builder_catalog.search(query)
                    search_samples_ms.append((perf_counter() - start) * 1000)
            search_samples_ms.sort()
            builder_search_keystroke_ms = {
                "median": round(search_samples_ms[len(search_samples_ms) // 2], 3),
                "p95": round(search_samples_ms[int(len(search_samples_ms) * 0.95)], 3),
                "maximum": round(search_samples_ms[-1], 3),
            }
            assert builder_search_keystroke_ms["p95"] < 8.0

            definition = BuilderDefinition(
                topic_groups=(
                    ("#AK_Step1_v12::^Systems::Renal",),
                    ("#AK_Step1_v12::#FirstAid::14_Renal",),
                ),
                tags=("High Yield", "Marked"),
                state_preset=StatePreset.DUE_NEW,
            )
            start = perf_counter()
            for _index in range(10_000):
                compile_builder_query(definition)
            builder_query_compile_10k_ms = milliseconds(start)

            print(
                json.dumps(
                    {
                        "scope": "synthetic local algorithms and Vellum SQLite only",
                        "database_initial_migration_ms": migration_ms,
                        "topic_cold_resolve_ms": topic_cold_ms,
                        "topic_hot_cache_10000_resolves_ms": topic_hot_10k_ms,
                        "timing_aggregate_100000_cards_ms": timing_100k_ms,
                        "recovery_standard_plan_ms": recovery_ms,
                        "study_builder_catalog_50000_tags_ms": builder_catalog_50k_tags_ms,
                        "study_builder_catalog_facets": {
                            "anking": len(builder_catalog.anking),
                            "raw_tags": len(builder_catalog.tags),
                        },
                        "study_builder_search_1000_queries_ms": builder_search_keystroke_ms,
                        "study_builder_query_compile_10000_ms": builder_query_compile_10k_ms,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            database.close()


if __name__ == "__main__":
    main()
