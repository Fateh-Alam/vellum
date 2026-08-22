"""Small synchronous event bus for decoupled feature communication."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
import logging
from threading import RLock
from typing import Any


EventHandler = Callable[..., None]


class EventBus:
    """Dispatch events in registration order and isolate handler failures."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()
        self._logger = logger or logging.getLogger("vellum.events")

    def subscribe(self, event: str, handler: EventHandler) -> Callable[[], None]:
        if not event or not callable(handler):
            raise ValueError("event and callable handler are required")
        with self._lock:
            if handler not in self._handlers[event]:
                self._handlers[event].append(handler)

        def unsubscribe() -> None:
            self.unsubscribe(event, handler)

        return unsubscribe

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(event)
            if not handlers:
                return
            try:
                handlers.remove(handler)
            except ValueError:
                return
            if not handlers:
                self._handlers.pop(event, None)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        with self._lock:
            handlers = tuple(self._handlers.get(event, ()))
        for handler in handlers:
            try:
                handler(*args, **kwargs)
            except Exception:
                self._logger.exception("Vellum event handler failed: %s", event)
