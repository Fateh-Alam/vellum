"""Deterministic hierarchical-tag parser with version-tolerant AnKing rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..core.config import TopicParsingConfig
from .ids import settings_hash, topic_id
from .models import ParsedTopicPath
from .normalization import (
    canonical_segment,
    display_segment,
    is_anking_container,
    is_probably_utility_root,
    match_key,
    source_key,
    split_hierarchical_tag,
)


PARSER_VERSION = 1


@dataclass(frozen=True)
class _Candidate:
    raw_tag: str
    source_root: str | None
    path_segments: tuple[str, ...]
    priority: int
    prefix_segments: tuple[str, ...]


class TopicParser:
    def __init__(self, config: TopicParsingConfig | None = None) -> None:
        self.config = config or TopicParsingConfig()
        self.settings_hash = settings_hash(self.config)
        self._preferred = {
            source_key(root): (index, root)
            for index, root in enumerate(self.config.preferred_roots)
        }
        self._ignored_roots = {match_key(root) for root in self.config.ignored_roots}
        self._ignored_segments = {
            canonical_segment(segment) for segment in self.config.ignored_segments
        }
        self._renames = {
            canonical_segment(segment): label
            for segment, label in self.config.renamed_segments.items()
        }
        self._badges = {
            source_key(root): label for root, label in self.config.source_badges.items()
        }

    def parse(self, tags: Iterable[str]) -> ParsedTopicPath:
        candidates = [candidate for tag in tags if (candidate := self._candidate(tag))]
        if not candidates:
            return ParsedTopicPath.empty()

        candidates.sort(
            key=lambda item: (
                item.priority,
                -len(item.path_segments),
                item.raw_tag.casefold(),
            )
        )
        selected = candidates[0]
        canonical, display, raw_prefixes = self._normalize_path(
            selected.path_segments, selected.prefix_segments
        )
        if not canonical:
            return ParsedTopicPath.empty()

        root = selected.source_root
        ancestors = tuple(
            topic_id(root, canonical[:index]) for index in range(1, len(canonical))
        )
        badges: list[str] = []
        for candidate in candidates:
            if candidate.source_root is None:
                continue
            badge = self._badges.get(
                source_key(candidate.source_root), display_segment(candidate.source_root)
            )
            if badge not in badges:
                badges.append(badge)

        return ParsedTopicPath(
            raw_tag=selected.raw_tag,
            source_root=root,
            path=display,
            canonical_path=canonical,
            topic_id=topic_id(root, canonical),
            ancestor_topic_ids=ancestors,
            source_badges=tuple(badges),
            raw_prefixes=raw_prefixes,
        )

    def preview(self, tags: Iterable[str]) -> str:
        result = self.parse(tags)
        return " → ".join(result.path) if result.found else "No topic context found"

    def _candidate(self, raw_tag: str) -> _Candidate | None:
        if not isinstance(raw_tag, str) or not raw_tag.strip():
            return None
        segments = list(split_hierarchical_tag(raw_tag))
        outer_prefix: tuple[str, ...] = ()
        if len(segments) < 2:
            return None

        if self.config.anking_adapter and segments and is_anking_container(segments[0]):
            outer_prefix = (segments.pop(0),)
        if len(segments) < 2:
            return None

        root_key = match_key(segments[0])
        if root_key in self._ignored_roots:
            return None
        if self.config.anking_adapter and is_probably_utility_root(segments[0]):
            return None

        root_matches: list[tuple[int, int, str]] = []
        for position, segment in enumerate(segments):
            preferred = self._preferred.get(source_key(segment))
            if preferred is not None and position < len(segments) - 1:
                root_matches.append((preferred[0], position, preferred[1]))
        if root_matches:
            priority, position, configured_root = min(root_matches)
            return _Candidate(
                raw_tag.strip(),
                configured_root,
                tuple(segments[position + 1 :]),
                priority,
                (*outer_prefix, *segments[: position + 1]),
            )

        if not self.config.generic_fallback:
            return None
        return _Candidate(
            raw_tag.strip(),
            None,
            tuple(segments),
            len(self._preferred) + 100,
            outer_prefix,
        )

    def _normalize_path(
        self, segments: tuple[str, ...], prefix_segments: tuple[str, ...]
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        canonical: list[str] = []
        display: list[str] = []
        prefixes: list[str] = []
        consumed: list[str] = []
        for segment in segments:
            consumed.append(segment)
            stable = canonical_segment(segment)
            if not stable or stable in self._ignored_segments:
                continue
            canonical.append(stable)
            display.append(self._renames.get(stable, display_segment(segment)))
            prefixes.append("::".join((*prefix_segments, *consumed)))
            if len(canonical) >= self.config.maximum_depth:
                break
        return tuple(canonical), tuple(display), tuple(prefixes)
