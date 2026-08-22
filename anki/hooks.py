"""Compatibility-isolated helper for registering and removing Anki hooks."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any


class HookRegistry:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._registrations: list[tuple[Any, Callable[..., Any]]] = []
        self._logger = logger or logging.getLogger("vellum.anki.hooks")

    def register(self, hook: Any, callback: Callable[..., Any]) -> bool:
        if hook is None or not hasattr(hook, "append"):
            self._logger.warning("Required Anki hook is unavailable")
            return False
        hook.append(callback)
        self._registrations.append((hook, callback))
        return True

    def clear(self) -> None:
        for hook, callback in reversed(self._registrations):
            try:
                hook.remove(callback)
            except (ValueError, AttributeError):
                pass
        self._registrations.clear()
