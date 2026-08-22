#!/usr/bin/env python3
"""Verify Vellum's Anki/Qt integration names in Anki's bundled runtime."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]


def load_vellum_namespace() -> None:
    package = types.ModuleType("vellum")
    package.__path__ = [str(ROOT)]
    package.__package__ = "vellum"
    sys.modules["vellum"] = package


def main() -> None:
    load_vellum_namespace()

    imported: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative.parts[0] in {"scripts", "tests"}:
            continue
        if relative == Path("__init__.py"):
            continue
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if not parts:
            continue
        module = "vellum." + ".".join(parts)
        importlib.import_module(module)
        imported.append(module)

    from aqt import gui_hooks, qt
    from aqt.filtered_deck import FilteredDeckConfigDialog
    from aqt.operations import QueryOp
    from aqt.operations.deck import remove_decks, set_current_deck
    from anki.decks import DeckManager

    hook_names = (
        "card_will_show",
        "deck_browser_did_render",
        "filtered_deck_dialog_did_add_or_update_deck",
        "overview_did_refresh",
        "overview_will_render_content",
        "profile_did_open",
        "profile_will_close",
        "reviewer_did_answer_card",
        "reviewer_did_show_question",
        "reviewer_will_end",
        "reviewer_will_show_context_menu",
        "state_shortcuts_will_change",
        "webview_did_receive_js_message",
        "webview_will_set_content",
    )
    missing_hooks = [name for name in hook_names if not hasattr(gui_hooks, name)]
    assert not missing_hooks, missing_hooks

    qt_names = (
        "QAbstractItemView",
        "QAction",
        "QButtonGroup",
        "QColor",
        "QCheckBox",
        "QComboBox",
        "QDialog",
        "QDialogButtonBox",
        "QDoubleSpinBox",
        "QFileDialog",
        "QFormLayout",
        "QFrame",
        "QGroupBox",
        "QHBoxLayout",
        "QKeySequence",
        "QLabel",
        "QLineEdit",
        "QListWidget",
        "QMenu",
        "QMessageBox",
        "QPlainTextEdit",
        "QPalette",
        "QPushButton",
        "QRadioButton",
        "QScrollArea",
        "QShortcut",
        "QSpinBox",
        "QSplitter",
        "QTabWidget",
        "QTableWidget",
        "QTableWidgetItem",
        "QTextBrowser",
        "QTimer",
        "QVBoxLayout",
        "QWidget",
        "qconnect",
    )
    missing_qt = [name for name in qt_names if not hasattr(qt, name)]
    assert not missing_qt, missing_qt

    assert QueryOp is not None
    assert set_current_deck is not None
    assert remove_decks is not None
    assert FilteredDeckConfigDialog is not None
    assert callable(getattr(DeckManager, "id_for_name", None))
    assert callable(getattr(DeckManager, "name_if_exists", None))

    print(
        json.dumps(
            {
                "anki_version": importlib.metadata.version("anki"),
                "imported_vellum_modules": len(set(imported)),
                "verified_gui_hooks": len(hook_names),
                "verified_qt_symbols": len(qt_names),
                "filtered_deck_dialog": True,
                "deck_operations": True,
                "deck_identity_apis": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
