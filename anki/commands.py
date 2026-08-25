"""Single source of truth for Vellum commands and cross-platform labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.config import VellumConfig
from .shortcuts import ShortcutAssignment, native_shortcut_label


@dataclass(frozen=True)
class CommandDefinition:
    name: str
    purpose: str
    module: str | None
    scope: str
    shortcut_path: tuple[str, str] | None = None
    fixed_shortcut: str | None = None


@dataclass(frozen=True)
class CommandView:
    name: str
    purpose: str
    scope: str
    portable_shortcut: str | None
    native_shortcut: str
    status: str
    detail: str


COMMANDS = (
    CommandDefinition("Context Sidebar", "Show or hide the current topic hierarchy.", "context", "Reviewer", ("context", "shortcut")),
    CommandDefinition("Recover Topic", "Build a temporary repair session from the current topic.", "recovery", "Reviewer", ("recovery", "shortcut")),
    CommandDefinition("Time Machine", "Plan a bounded session from available time.", "time_machine", "Anywhere", ("time_machine", "shortcut")),
    CommandDefinition("Study Builder", "Build a scheduled deck by choosing topics and source decks, or decks and their tags.", "study_builder", "Anywhere", ("study_builder", "shortcut")),
    CommandDefinition("Backtrack", "Open the previous card and topic read-only.", "backtrack", "Anywhere", ("backtrack", "shortcut")),
    CommandDefinition("Mind Note", "Save a private thought against the current topic.", "mind_notes", "Anywhere", ("mind_notes", "shortcut")),
    CommandDefinition("Collapse Context", "Close the expanded Context panel.", "context", "Reviewer panel", ("context", "collapse_shortcut")),
    CommandDefinition("Recovery modes", "Choose Quick, Standard, Full, or Custom.", "recovery", "Recovery dialog", fixed_shortcut="1–4"),
    CommandDefinition("Resume Last Session", "Assess and continue an interrupted session.", "resume", "Vellum menu"),
    CommandDefinition("Return Ramp", "Open a bounded re-entry after an absence.", "return_ramp", "Vellum menu"),
    CommandDefinition("Finish Current Session", "Safely return remaining generated cards home.", None, "Vellum menu"),
    CommandDefinition("Session History", "Open learner summaries and technical manifests.", "session_debrief", "Vellum menu"),
    CommandDefinition("Settings", "Configure every Vellum module.", None, "Vellum menu"),
    CommandDefinition("Commands & Help", "Open this offline guide.", None, "Vellum menu"),
)


def command_views(config: VellumConfig, mw: Any | None = None) -> tuple[CommandView, ...]:
    runtime = getattr(mw, "_vellum_shortcut_states", {}) if mw is not None else {}
    result: list[CommandView] = []
    for command in COMMANDS:
        portable = command.fixed_shortcut
        if command.shortcut_path is not None:
            section, field = command.shortcut_path
            portable = str(getattr(getattr(config, section), field))
        enabled_module = command.module is None or config.modules.enabled(command.module)
        if not enabled_module:
            state, detail = "Module disabled", "Enable this module in Vellum Settings."
        elif (
            command.shortcut_path is not None
            and hasattr(getattr(config, command.shortcut_path[0]), "shortcut_enabled")
            and not getattr(getattr(config, command.shortcut_path[0]), "shortcut_enabled")
        ):
            state, detail = "Disabled", "Enable this command in Vellum Settings."
        elif command.shortcut_path is not None and not config.general.keyboard_shortcuts:
            state, detail = "Globally disabled", "Vellum keyboard shortcuts are disabled."
        else:
            assignment = runtime.get(command.name)
            if not isinstance(assignment, ShortcutAssignment):
                feature_aliases = {
                    "Context Sidebar": "Context",
                    "Recover Topic": "Recovery",
                    "Time Machine": "Time Machine",
                    "Study Builder": "Study Builder",
                    "Backtrack": "Backtrack",
                    "Mind Note": "Mind Notes",
                }
                assignment = runtime.get(feature_aliases.get(command.name, ""))
            if isinstance(assignment, ShortcutAssignment):
                if assignment.state == "conflicted":
                    state, detail = "Conflict", assignment.reason
                elif assignment.state == "disabled":
                    state, detail = "Disabled", assignment.reason
                else:
                    state, detail = "Ready", "Available in its listed scope."
            elif command.scope == "Reviewer":
                state, detail = "Awaiting Reviewer", "Conflicts are checked when Reviewer opens."
            else:
                state, detail = "Ready", "Available in its listed scope."
        result.append(
            CommandView(
                name=command.name,
                purpose=command.purpose,
                scope=command.scope,
                portable_shortcut=portable,
                native_shortcut=(
                    command.fixed_shortcut
                    if command.fixed_shortcut
                    else native_shortcut_label(portable or "") if portable else "—"
                ),
                status=state,
                detail=detail,
            )
        )
    return tuple(result)
