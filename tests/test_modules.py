import logging
from types import SimpleNamespace
import unittest

from vellum.bootstrap import VellumApplication
from vellum.core.config import ModuleFlags, VellumConfig
from vellum.core.modules import ModuleRegistry, PlaceholderModule


class ModuleRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger("vellum.tests.modules")
        logger.addHandler(logging.NullHandler())
        self.registry = ModuleRegistry(logger=logger)
        for name in ModuleFlags.__dataclass_fields__:
            self.registry.register(PlaceholderModule(name, logger=logger))

    def test_database_failure_keeps_only_nonpersistent_context_surface(self) -> None:
        app = VellumApplication(
            "vellum",
            SimpleNamespace(persistence_available=False),  # type: ignore[arg-type]
        )
        effective = app.effective_modules(VellumConfig())
        self.assertTrue(effective.context)
        self.assertFalse(effective.recovery)
        self.assertFalse(effective.time_machine)
        self.assertFalse(effective.hud)
        self.assertFalse(effective.resume)
        self.assertFalse(effective.return_ramp)
        self.assertTrue(effective.backtrack)
        self.assertFalse(effective.mind_notes)
        self.assertFalse(effective.topic_health)
        self.assertFalse(effective.home_panel)

    def test_each_module_can_run_alone(self) -> None:
        names = tuple(ModuleFlags.__dataclass_fields__)
        for active in names:
            flags = ModuleFlags(**{name: name == active for name in names})
            self.registry.reconcile(flags)
            self.assertEqual(self.registry.running_names(), frozenset({active}))

    def test_all_visible_modules_can_be_disabled(self) -> None:
        names = tuple(ModuleFlags.__dataclass_fields__)
        self.registry.reconcile(ModuleFlags())
        self.registry.reconcile(ModuleFlags(**{name: False for name in names}))
        self.assertEqual(self.registry.running_names(), frozenset())

    def test_duplicate_module_registration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.register(PlaceholderModule("context"))


if __name__ == "__main__":
    unittest.main()
