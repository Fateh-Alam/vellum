"""Lifecycle management for independently enabled Vellum modules."""

from __future__ import annotations

import logging
from typing import Protocol

from .config import ModuleFlags


class FeatureModule(Protocol):
    name: str

    @property
    def running(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


class PlaceholderModule:
    """Lifecycle marker replaced by each real feature in later phases."""

    def __init__(self, name: str, logger: logging.Logger | None = None) -> None:
        self.name = name
        self._running = False
        self._logger = logger or logging.getLogger(f"vellum.modules.{name}")

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._logger.debug("Module enabled: %s", self.name)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._logger.debug("Module disabled: %s", self.name)


class ModuleRegistry:
    """Starts only enabled modules and never assumes cross-feature imports."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._modules: dict[str, FeatureModule] = {}
        self._logger = logger or logging.getLogger("vellum.modules")

    def register(self, module: FeatureModule) -> None:
        if not module.name or module.name in self._modules:
            raise ValueError(f"Module already registered or unnamed: {module.name!r}")
        self._modules[module.name] = module

    def reconcile(self, flags: ModuleFlags) -> None:
        for name, module in self._modules.items():
            should_run = flags.enabled(name)
            try:
                if should_run and not module.running:
                    module.start()
                elif not should_run and module.running:
                    module.stop()
            except Exception:
                self._logger.exception("Vellum module lifecycle failed: %s", name)

    def stop_all(self) -> None:
        for name, module in reversed(tuple(self._modules.items())):
            if not module.running:
                continue
            try:
                module.stop()
            except Exception:
                self._logger.exception("Vellum module shutdown failed: %s", name)

    def running_names(self) -> frozenset[str]:
        return frozenset(name for name, module in self._modules.items() if module.running)

    def get(self, name: str) -> FeatureModule | None:
        return self._modules.get(name)

    def restart_enabled(self, flags: ModuleFlags) -> None:
        """Apply runtime configuration that is bound during module start."""

        self.stop_all()
        self.reconcile(flags)
