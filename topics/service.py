"""Shared topic service used independently by Context and Recovery."""

from __future__ import annotations

from collections.abc import Iterable

from ..core.events import EventBus
from .cache import TopicPathCache
from .models import ParsedTopicPath
from .parser import PARSER_VERSION, TopicParser


class TopicService:
    def __init__(
        self,
        parser: TopicParser,
        cache: TopicPathCache | None = None,
        events: EventBus | None = None,
    ) -> None:
        self.parser = parser
        self.cache = cache
        self.events = events

    def resolve(self, note_id: int, tags: Iterable[str]) -> ParsedTopicPath:
        stable_tags = tuple(tags)
        if self.cache is not None:
            cached = self.cache.get(
                note_id,
                stable_tags,
                PARSER_VERSION,
                self.parser.settings_hash,
            )
            if cached is not None:
                return cached

        result = self.parser.parse(stable_tags)
        if self.cache is not None:
            self.cache.put(
                note_id,
                stable_tags,
                PARSER_VERSION,
                self.parser.settings_hash,
                result,
            )
        if self.events is not None:
            self.events.emit("topic_resolved", note_id, result)
        return result

    def preview(self, tags: Iterable[str]) -> str:
        return self.parser.preview(tags)

    def invalidate(self, note_id: int | None = None) -> None:
        if self.cache is not None:
            self.cache.invalidate(note_id)

    def reconfigure(self, parser: TopicParser) -> None:
        """Atomically replace parsing rules and invalidate incompatible cache."""

        if parser.settings_hash == self.parser.settings_hash:
            return
        self.parser = parser
        self.invalidate()

    def recent_topics(self, limit: int = 12) -> tuple[ParsedTopicPath, ...]:
        if self.cache is None:
            return ()
        return self.cache.recent_topics(limit)
