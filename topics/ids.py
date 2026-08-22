"""Stable identifiers and cache signatures for topic paths."""

from __future__ import annotations

from hashlib import sha1, sha256
import json
from typing import Iterable

from ..core.config import TopicParsingConfig
from .normalization import canonical_segment


def topic_id(source_root: str | None, canonical_path: Iterable[str]) -> str:
    root = canonical_segment(source_root or "generic")
    path = "/".join(canonical_path)
    return sha1(f"{root}|{path}".encode("utf-8")).hexdigest()


def tag_signature(tags: Iterable[str]) -> str:
    stable = "\n".join(sorted({tag.strip() for tag in tags if tag.strip()}))
    return sha256(stable.encode("utf-8")).hexdigest()


def settings_hash(config: TopicParsingConfig) -> str:
    payload = {
        "preferred_roots": config.preferred_roots,
        "ignored_roots": config.ignored_roots,
        "ignored_segments": config.ignored_segments,
        "renamed_segments": config.renamed_segments,
        "source_badges": config.source_badges,
        "maximum_depth": config.maximum_depth,
        "anking_adapter": config.anking_adapter,
        "generic_fallback": config.generic_fallback,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()
