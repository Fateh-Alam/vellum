#!/usr/bin/env python3
"""Evaluate recent Vellum topics against a copied Anki collection.

Both SQLite databases are copied with the online backup API. Only the copies
are opened for analysis, and no card or note field content is printed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import types


ROOT = Path(__file__).resolve().parents[1]


def backup(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def load_vellum_namespace() -> None:
    package = types.ModuleType("vellum")
    package.__path__ = [str(ROOT)]
    package.__package__ = "vellum"
    sys.modules["vellum"] = package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("collection", type=Path)
    parser.add_argument("vellum_database", type=Path)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    from anki.collection import Collection

    load_vellum_namespace()
    from vellum.anki.topic_stats import collect_topic_stats
    from vellum.topics.models import ParsedTopicPath

    with tempfile.TemporaryDirectory(prefix="vellum-health-diagnostic-") as temp:
        temp_path = Path(temp)
        collection_path = temp_path / "collection.anki2"
        vellum_path = temp_path / "vellum.sqlite3"
        backup(args.collection, collection_path)
        backup(args.vellum_database, vellum_path)

        vellum = sqlite3.connect(vellum_path)
        vellum.row_factory = sqlite3.Row
        rows = list(
            vellum.execute(
                "SELECT result_json, updated_at FROM topic_path_cache "
                "ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(args.limit) * 8, 400)),),
            )
        )
        vellum.close()

        recent: list[ParsedTopicPath] = []
        seen: set[str] = set()
        for row in rows:
            try:
                parsed = ParsedTopicPath.from_mapping(json.loads(row["result_json"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if (
                not parsed.found
                or not parsed.topic_id
                or not parsed.raw_tag
                or parsed.topic_id in seen
            ):
                continue
            seen.add(parsed.topic_id)
            recent.append(parsed)
            if len(recent) >= max(1, int(args.limit)):
                break

        collection = Collection(str(collection_path))
        try:
            started = time.perf_counter()
            output: list[dict[str, object]] = []
            for parsed in recent:
                stats = collect_topic_stats(collection, parsed.raw_tag)
                output.append(
                    {
                        "topic": " > ".join(parsed.path),
                        "health": stats.health_state,
                        "total": stats.total_cards,
                        "due": stats.due_cards,
                        "recent_reviews_last_50": stats.recent_reviews,
                        "recent_again_cards_14d": stats.recent_failures,
                        "retention_last_50": (
                            round(stats.retention_estimate, 4)
                            if stats.retention_estimate is not None
                            else None
                        ),
                    }
                )
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(
                json.dumps(
                    {
                        "topics_evaluated": len(output),
                        "elapsed_ms": round(elapsed_ms, 3),
                        "states": {
                            state: sum(item["health"] == state for item in output)
                            for state in (
                                "Strong",
                                "Stable",
                                "Fading",
                                "Needs Recovery",
                                "Insufficient Data",
                            )
                        },
                        "topics": output,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            collection.close(downgrade=False)


if __name__ == "__main__":
    main()
