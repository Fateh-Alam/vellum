"""Conflict-aware Qt shortcut assignment shared by independent modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ShortcutAssignment:
    state: str
    portable: str
    reason: str = ""

    def __bool__(self) -> bool:
        return self.state == "active"


def _record(owner: Any | None, feature_name: str, assignment: ShortcutAssignment) -> None:
    if owner is None:
        return
    states = getattr(owner, "_vellum_shortcut_states", None)
    if not isinstance(states, dict):
        states = {}
        setattr(owner, "_vellum_shortcut_states", states)
    states[feature_name] = assignment


def native_shortcut_label(shortcut: str) -> str:
    """Render one portable Qt sequence using the host platform's conventions."""

    if not shortcut.strip():
        return "—"
    try:
        from aqt.qt import QKeySequence  # type: ignore[import-not-found]

        sequence = QKeySequence(shortcut)
        formats = getattr(QKeySequence, "SequenceFormat", None)
        native = getattr(formats, "NativeText", None) if formats is not None else None
        rendered = sequence.toString(native) if native is not None else sequence.toString()
        return str(rendered or shortcut)
    except Exception:
        return shortcut


def append_state_shortcut(
    shortcuts: list[tuple[Any, ...]],
    shortcut: str,
    callback: Any,
    *,
    enabled: bool,
    logger: logging.Logger,
    feature_name: str,
    owner: Any | None = None,
) -> ShortcutAssignment:
    """Append a state-local shortcut only when Anki/add-ons have not claimed it."""

    if not enabled or not shortcut.strip():
        assignment = ShortcutAssignment("disabled", shortcut, "Shortcut is disabled")
        _record(owner, feature_name, assignment)
        return assignment
    from aqt.qt import QKeySequence  # type: ignore[import-not-found]

    requested = QKeySequence(shortcut)
    for existing in shortcuts:
        if not existing:
            continue
        try:
            if QKeySequence(existing[0]) == requested:
                logger.warning(
                    "%s shortcut %s conflicts in the Reviewer; disabled",
                    feature_name,
                    shortcut,
                )
                assignment = ShortcutAssignment(
                    "conflicted", shortcut, "Already used in the Reviewer"
                )
                _record(owner, feature_name, assignment)
                return assignment
        except Exception:
            continue
    shortcuts.append((shortcut, callback))
    assignment = ShortcutAssignment("active", shortcut)
    _record(owner, feature_name, assignment)
    return assignment


def assign_shortcut(
    action: Any,
    mw: Any,
    shortcut: str,
    *,
    enabled: bool,
    logger: logging.Logger,
    feature_name: str,
) -> ShortcutAssignment:
    action.setShortcut("")
    if not enabled or not shortcut.strip():
        assignment = ShortcutAssignment("disabled", shortcut, "Shortcut is disabled")
        _record(mw, feature_name, assignment)
        return assignment
    from aqt.qt import (  # type: ignore[import-not-found]
        QAction,
        QKeySequence,
        QShortcut,
    )

    requested = QKeySequence(shortcut)
    for existing in mw.findChildren(QAction):
        if existing is action:
            continue
        try:
            if any(sequence == requested for sequence in existing.shortcuts()):
                logger.warning(
                    "%s shortcut %s conflicts with another Anki action; disabled",
                    feature_name,
                    shortcut,
                )
                action.setStatusTip(
                    f"Shortcut {shortcut} is already used; change it in Vellum Settings."
                )
                assignment = ShortcutAssignment(
                    "conflicted", shortcut, "Already used by another Anki action"
                )
                _record(mw, feature_name, assignment)
                return assignment
        except Exception:
            continue
    for existing in mw.findChildren(QShortcut):
        try:
            if existing.key() == requested:
                logger.warning(
                    "%s shortcut %s conflicts with an Anki/add-on shortcut; disabled",
                    feature_name,
                    shortcut,
                )
                action.setStatusTip(
                    f"Shortcut {shortcut} is already used; change it in Vellum Settings."
                )
                assignment = ShortcutAssignment(
                    "conflicted", shortcut, "Already used by an Anki add-on"
                )
                _record(mw, feature_name, assignment)
                return assignment
        except Exception:
            continue
    action.setShortcut(requested)
    action.setStatusTip("")
    assignment = ShortcutAssignment("active", shortcut)
    _record(mw, feature_name, assignment)
    return assignment
