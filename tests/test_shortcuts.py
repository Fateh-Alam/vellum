import logging
from dataclasses import replace
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from vellum.anki.commands import command_views
from vellum.anki.shortcuts import (
    ShortcutAssignment,
    append_state_shortcut,
    assign_shortcut,
    native_shortcut_label,
)
from vellum.core.config import VellumConfig


class FakeKeySequence:
    class SequenceFormat:
        NativeText = "native"

    def __init__(self, value="") -> None:
        self.value = value.value if isinstance(value, FakeKeySequence) else str(value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FakeKeySequence) and self.value == other.value

    def toString(self, mode=None) -> str:
        return f"native:{self.value}" if mode == "native" else self.value


class FakeAction:
    def __init__(self, shortcuts=()) -> None:
        self._shortcuts = [FakeKeySequence(value) for value in shortcuts]
        self.status_tip = ""

    def setShortcut(self, value) -> None:
        sequence = FakeKeySequence(value)
        self._shortcuts = [] if not sequence.value else [sequence]

    def shortcuts(self):
        return list(self._shortcuts)

    def setStatusTip(self, value: str) -> None:
        self.status_tip = value


class FakeShortcut:
    def __init__(self, key: str) -> None:
        self._key = FakeKeySequence(key)

    def key(self):
        return self._key


class FakeWindow:
    def __init__(self, actions=(), shortcuts=()) -> None:
        self.actions = list(actions)
        self.shortcuts = list(shortcuts)

    def findChildren(self, kind):
        if kind is FakeAction:
            return self.actions
        if kind is FakeShortcut:
            return self.shortcuts
        return []


def fake_aqt_modules() -> dict[str, ModuleType]:
    aqt = ModuleType("aqt")
    qt = ModuleType("aqt.qt")
    qt.QAction = FakeAction
    qt.QKeySequence = FakeKeySequence
    qt.QShortcut = FakeShortcut
    aqt.qt = qt
    return {"aqt": aqt, "aqt.qt": qt}


class ShortcutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("vellum.tests.shortcuts")

    def test_state_shortcut_refuses_an_existing_reviewer_key(self) -> None:
        shortcuts = [("C", lambda: None)]
        with patch.dict(sys.modules, fake_aqt_modules()):
            added = append_state_shortcut(
                shortcuts,
                "C",
                lambda: None,
                enabled=True,
                logger=self.logger,
                feature_name="Context",
            )
        self.assertFalse(added)
        self.assertEqual(len(shortcuts), 1)

    def test_state_shortcut_appends_when_free(self) -> None:
        shortcuts = [("Space", lambda: None)]
        with patch.dict(sys.modules, fake_aqt_modules()):
            added = append_state_shortcut(
                shortcuts,
                "Shift+C",
                lambda: None,
                enabled=True,
                logger=self.logger,
                feature_name="Recovery",
            )
        self.assertTrue(added)
        self.assertEqual(shortcuts[-1][0], "Shift+C")

    def test_global_action_refuses_qaction_and_qshortcut_collisions(self) -> None:
        with patch.dict(sys.modules, fake_aqt_modules()):
            for window in (
                FakeWindow(actions=(FakeAction(("T",)),)),
                FakeWindow(shortcuts=(FakeShortcut("T"),)),
            ):
                action = FakeAction()
                added = assign_shortcut(
                    action,
                    window,
                    "T",
                    enabled=True,
                    logger=self.logger,
                    feature_name="Time Machine",
                )
                self.assertFalse(added)
                self.assertFalse(action.shortcuts())
                self.assertIn("already used", action.status_tip)

    def test_global_action_assigns_when_free(self) -> None:
        action = FakeAction()
        with patch.dict(sys.modules, fake_aqt_modules()):
            added = assign_shortcut(
                action,
                FakeWindow(),
                "Ctrl+Shift+T",
                enabled=True,
                logger=self.logger,
                feature_name="Time Machine",
            )
        self.assertTrue(added)
        self.assertEqual(action.shortcuts(), [FakeKeySequence("Ctrl+Shift+T")])
        self.assertEqual(action.status_tip, "")

    def test_native_labels_are_delegated_to_qt(self) -> None:
        with patch.dict(sys.modules, fake_aqt_modules()):
            self.assertEqual(native_shortcut_label("Alt+M"), "native:Alt+M")

    def test_command_catalog_reports_global_module_feature_and_conflict_states(self) -> None:
        config = VellumConfig()
        globally_off = replace(
            config, general=replace(config.general, keyboard_shortcuts=False)
        )
        self.assertEqual(
            next(item for item in command_views(globally_off) if item.name == "Time Machine").status,
            "Globally disabled",
        )
        module_off = replace(
            config, modules=replace(config.modules, mind_notes=False)
        )
        self.assertEqual(
            next(item for item in command_views(module_off) if item.name == "Mind Note").status,
            "Module disabled",
        )
        feature_off = replace(
            config, backtrack=replace(config.backtrack, shortcut_enabled=False)
        )
        self.assertEqual(
            next(item for item in command_views(feature_off) if item.name == "Backtrack").status,
            "Disabled",
        )
        window = SimpleNamespace(
            _vellum_shortcut_states={
                "Context": ShortcutAssignment("conflicted", "C", "Already used")
            }
        )
        self.assertEqual(
            next(item for item in command_views(config, window) if item.name == "Context Sidebar").status,
            "Conflict",
        )


if __name__ == "__main__":
    unittest.main()
