"""Lifecycle gate for the independently optional Topic Health heuristic."""

from __future__ import annotations

import logging


class TopicHealthModule:
    """Owns enablement; Context, Home, and overview consume the pure classifier."""

    name = "topic_health"

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("vellum.features.topic_health")
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._logger.info("Topic Health heuristic enabled")

    def stop(self) -> None:
        self._running = False
