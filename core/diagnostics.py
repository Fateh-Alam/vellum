"""Privacy-preserving local diagnostics and explicit Vellum-data resets."""

from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from typing import Any

from .config import VellumConfig
from .db import Database
from .release import VELLUM_VERSION


RESET_TABLES = (
    "session_mind_note_events",
    "session_debriefs",
    "mind_notes",
    "app_activity",
    "generated_deck_card_answers",
    "generated_deck_cards",
    "generated_deck_history",
    "session_cards",
    "sessions",
    "timing_samples",
    "timing_stats",
    "topic_path_cache",
    "topic_cache",
    "user_topic_overrides",
)


def anonymized_config(config: VellumConfig) -> dict[str, Any]:
    """Include operational switches and ranges, but not user tag names."""

    return {
        "config_version": config.config_version,
        "enabled": config.enabled,
        "modules": config.modules.__dict__,
        "general": config.general.__dict__,
        "context": config.context.__dict__,
        "hud": config.hud.__dict__,
        "time_machine": {
            **config.time_machine.__dict__,
            "fallback_seconds": config.time_machine.fallback_seconds.__dict__,
        },
        "resume": config.resume.__dict__,
        "return_ramp": config.return_ramp.__dict__,
        "backtrack": config.backtrack.__dict__,
        "mind_notes": config.mind_notes.__dict__,
        "debrief": config.debrief.__dict__,
        "recovery": {
            **config.recovery.__dict__,
            "deck_name_pattern": "<redacted pattern>",
        },
        "home": config.home.__dict__,
        "topic_parsing": {
            "preferred_root_count": len(config.topic_parsing.preferred_roots),
            "ignored_root_count": len(config.topic_parsing.ignored_roots),
            "ignored_segment_count": len(config.topic_parsing.ignored_segments),
            "rename_count": len(config.topic_parsing.renamed_segments),
            "maximum_depth": config.topic_parsing.maximum_depth,
            "anking_adapter": config.topic_parsing.anking_adapter,
            "generic_fallback": config.topic_parsing.generic_fallback,
        },
    }


def recent_problem_logs(path: Path, limit: int = 100) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    problems = [line for line in lines if " ERROR " in line or " WARNING " in line]
    home = str(Path.home())
    return [
        re.sub(r"\b(nid|cid|card_id|note_id)=?\d+\b", r"\1=<redacted>", line).replace(
            home, "<home>"
        )
        for line in problems[-limit:]
    ]


def build_diagnostics(
    *,
    config: VellumConfig,
    database: Database,
    log_path: Path,
    anki_version: str,
) -> dict[str, Any]:
    return {
        "vellum_version": VELLUM_VERSION,
        "anki_version": anki_version,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "database_schema": database.schema_version,
        "config": anonymized_config(config),
        "recent_problem_logs": recent_problem_logs(log_path),
        "privacy": "No card text, note fields, collection path, or tag names included.",
    }


def write_diagnostics(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clear_vellum_data(database: Database, tables: tuple[str, ...]) -> None:
    if not tables or any(table not in RESET_TABLES for table in tables):
        raise ValueError("Only explicit Vellum-owned tables may be cleared")
    with database.locked() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            for table in tables:
                connection.execute(f"DELETE FROM {table}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def clear_mind_note_data(database: Database) -> None:
    """Remove Mind Notes from both live tables and durable Debrief snapshots."""

    with database.locked() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE session_debriefs SET mind_notes_json = '[]'")
            connection.execute("DELETE FROM session_mind_note_events")
            connection.execute("DELETE FROM mind_notes")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
