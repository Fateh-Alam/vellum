"""Structured Vellum settings, parser preview, data controls, and diagnostics."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from ..core.config import (
    FallbackSeconds,
    MAX_ABSENCE_DAYS,
    ModuleFlags,
    TopicParsingConfig,
)
from ..core.diagnostics import (
    RESET_TABLES,
    build_diagnostics,
    clear_mind_note_data,
    clear_vellum_data,
    write_diagnostics,
)
from ..sessions.models import TERMINAL_STATUSES

if TYPE_CHECKING:
    from ..bootstrap import VellumApplication


SESSION_SAFETY_TABLES = frozenset(
    {
        "sessions",
        "session_cards",
        "session_debriefs",
        "session_mind_note_events",
        "generated_deck_history",
        "generated_deck_cards",
        "generated_deck_card_answers",
    }
)


def reset_would_break_active_session(app: Any, tables: tuple[str, ...]) -> bool:
    """Protect active deck identity before deleting its safety evidence."""

    if not SESSION_SAFETY_TABLES.intersection(tables):
        return False
    session = getattr(getattr(app.services, "sessions", None), "current", None)
    return session is not None and session.status not in TERMINAL_STATUSES


MODULE_LABELS = {
    "context": ("Context Sidebar", "See the topic hierarchy while reviewing."),
    "recovery": ("Topic Recovery", "Repair a broader gap from the current card."),
    "time_machine": ("Study by Time", "Plan a session from the time you have available."),
    "study_builder": (
        "Study Builder",
        "Build scheduled study decks from card text, decks, topics, and tags.",
    ),
    "hud": ("Session HUD", "Show quiet progress and time while reviewing."),
    "resume": ("Resume", "Continue interrupted study context."),
    "return_ramp": (
        "Return Ramp",
        "Offer a calm, bounded re-entry after a configurable absence.",
    ),
    "backtrack": (
        "Backtrack",
        "Revisit the previous card or topic without changing scheduling.",
    ),
    "mind_notes": (
        "Mind Notes",
        "Save local topic-linked thoughts and resurface them later.",
    ),
    "session_debrief": (
        "Session Debrief",
        "Turn completed study into a useful summary and optional handoff.",
    ),
    "topic_health": ("Topic Health", "Show a conservative recent-performance heuristic."),
    "home_panel": ("Home Panel", "Add continuity controls to the deck browser."),
}


def install_settings_action(mw: Any, app: "VellumApplication") -> Any:
    from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

    action = QAction("Vellum Settings…", mw)
    qconnect(action.triggered, lambda: show_settings(mw, app))
    mw.form.menuTools.addAction(action)
    return action


def _combo(widget: Any, values: Iterable[tuple[str, str]], selected: str) -> None:
    for label, value in values:
        widget.addItem(label, value)
    widget.setCurrentIndex(max(0, widget.findData(selected)))


def _lines(widget: Any) -> tuple[str, ...]:
    result: list[str] = []
    for line in widget.toPlainText().splitlines():
        value = line.strip()
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _key_value_lines(widget: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in widget.toPlainText().splitlines():
        if "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key and value:
            result[key] = value
    return result


def show_settings(
    parent: Any, app: "VellumApplication", initial_tab: str | None = None
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QTabWidget,
        QVBoxLayout,
        QWidget,
        qconnect,
    )
    from aqt.utils import askUser, showInfo, showWarning, tooltip  # type: ignore[import-not-found]

    config = app.config
    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Settings")
    dialog.resize(780, 650)
    outer = QVBoxLayout(dialog)
    heading = QLabel("Vellum")
    heading.setStyleSheet("font-size: 22px; font-weight: 650;")
    outer.addWidget(heading)
    subtitle = QLabel(
        "A local-first study-continuity layer. Changes apply when you choose Save."
    )
    subtitle.setWordWrap(True)
    outer.addWidget(subtitle)
    if not app.services.persistence_available:
        storage_warning = QLabel(
            "Vellum could not open its private database. Context remains available, "
            "and Backtrack works in memory, but Recovery, Study by Time, HUD, Resume, "
            "Return Ramp, Mind Notes, Topic Health, and Home are disabled for this run."
            " Session Debrief and Study Builder are also unavailable until persistent "
            "storage returns."
        )
        storage_warning.setWordWrap(True)
        storage_warning.setStyleSheet("color: #9a5a2c;")
        outer.addWidget(storage_warning)
    tabs = QTabWidget()
    outer.addWidget(tabs, 1)

    def form_tab(name: str) -> Any:
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setWidget(content)
        tabs.addTab(page, name)
        return form

    general_form = form_tab("General")
    enabled = QCheckBox("Enable Vellum")
    enabled.setChecked(config.enabled)
    show_menu = QCheckBox("Show the Vellum menu")
    show_menu.setChecked(config.general.show_menu)
    keyboard_shortcuts = QCheckBox("Enable Vellum keyboard shortcuts")
    keyboard_shortcuts.setChecked(config.general.keyboard_shortcuts)
    animations = QCheckBox("Enable animations")
    animations.setChecked(config.general.animations)
    reduced = QCheckBox("Reduce motion")
    reduced.setChecked(config.general.reduced_motion)
    debug = QCheckBox("Debug logging")
    debug.setChecked(config.general.debug_logging)
    theme = QComboBox()
    _combo(theme, (("Automatic", "auto"), ("Light", "light"), ("Dark", "dark")), config.general.theme)
    for widget in (
        enabled,
        show_menu,
        keyboard_shortcuts,
        animations,
        reduced,
        debug,
    ):
        general_form.addRow(widget)
    general_form.addRow("Theme", theme)
    help_button = QPushButton("Open Commands && Help")
    from .help import show_help

    qconnect(help_button.clicked, lambda: show_help(parent, app, initial_section="Commands"))
    general_form.addRow(help_button)

    modules_page = QWidget()
    modules_layout = QVBoxLayout(modules_page)
    modules_layout.addWidget(QLabel("Every module has its own lifecycle and can run alone."))
    module_boxes: dict[str, Any] = {}
    for name, (label, explanation) in MODULE_LABELS.items():
        box = QCheckBox(label)
        box.setChecked(config.modules.enabled(name))
        box.setToolTip(explanation)
        module_boxes[name] = box
        modules_layout.addWidget(box)
        detail = QLabel(explanation)
        detail.setStyleSheet("margin-left: 22px;")
        modules_layout.addWidget(detail)
    modules_layout.addStretch(1)
    tabs.addTab(modules_page, "Modules")

    context_form = form_tab("Context")
    context_side = QComboBox()
    _combo(context_side, (("Right", "right"), ("Left", "left")), config.context.side)
    context_state = QComboBox()
    _combo(context_state, (("Collapsed", "collapsed"), ("Expanded", "expanded"), ("Remember", "remember")), config.context.default_state)
    context_width = QSpinBox()
    context_width.setRange(220, 480)
    context_width.setValue(config.context.width)
    context_width.setSuffix(" px")
    context_shortcut_enabled = QCheckBox("Enable reviewer shortcut")
    context_shortcut_enabled.setChecked(config.context.shortcut_enabled)
    context_shortcut = QLineEdit(config.context.shortcut)
    collapse_shortcut = QLineEdit(config.context.collapse_shortcut)
    auto_collapse = QCheckBox("Auto-collapse on each new card")
    auto_collapse.setChecked(config.context.auto_collapse_on_new_card)
    context_pinned = QCheckBox("Keep Context pinned open")
    context_pinned.setChecked(config.context.pinned)
    context_checks: dict[str, Any] = {}
    for field_name, label in (
        ("show_title", "Show topic title"),
        ("show_breadcrumbs", "Show breadcrumbs"),
        ("show_card_count", "Show card count"),
        ("show_maturity_breakdown", "Show maturity breakdown"),
        ("show_retention", "Show retention when available"),
        ("show_recent_failures", "Show recent failures"),
        ("show_source_badges", "Show source badges"),
        ("show_health", "Show Topic Health"),
        ("show_recovery", "Show Recover Topic button"),
    ):
        box = QCheckBox(label)
        box.setChecked(bool(getattr(config.context, field_name)))
        context_checks[field_name] = box
        context_form.addRow(box)
    context_form.addRow("Panel side", context_side)
    context_form.addRow("Default state", context_state)
    context_form.addRow("Width", context_width)
    context_form.addRow(auto_collapse)
    context_form.addRow(context_pinned)
    context_form.addRow(context_shortcut_enabled)
    context_form.addRow("Toggle shortcut", context_shortcut)
    context_form.addRow("Collapse shortcut", collapse_shortcut)

    recovery_form = form_tab("Recovery")
    recovery_shortcut_enabled = QCheckBox("Enable keyboard shortcut")
    recovery_shortcut_enabled.setChecked(config.recovery.shortcut_enabled)
    recovery_shortcut = QLineEdit(config.recovery.shortcut)
    recovery_level = QComboBox()
    _combo(recovery_level, (("Current topic", "current"), ("Remember last level", "remember_last")), config.recovery.default_level)
    recovery_mode = QComboBox()
    _combo(recovery_mode, (("Quick", "quick"), ("Standard", "standard"), ("Full", "full")), config.recovery.default_mode)
    include_new = QCheckBox("Include new cards")
    include_new.setChecked(config.recovery.include_new)
    include_current = QCheckBox("Include current card")
    include_current.setChecked(config.recovery.include_current)
    failure_days = QSpinBox()
    failure_days.setRange(1, 365)
    failure_days.setValue(config.recovery.recent_failure_days)
    failure_days.setSuffix(" days")
    max_quick = QSpinBox()
    max_quick.setRange(4, 8)
    max_quick.setValue(config.recovery.max_quick)
    max_standard = QSpinBox()
    max_standard.setRange(8, 500)
    max_standard.setValue(config.recovery.max_standard)
    ask_before = QCheckBox("Ask before opening Anki's filtered-deck window")
    ask_before.setChecked(config.recovery.ask_before_create)
    deck_pattern = QLineEdit(config.recovery.deck_name_pattern)
    recovery_form.addRow(recovery_shortcut_enabled)
    recovery_form.addRow("Shortcut", recovery_shortcut)
    recovery_form.addRow("Default level", recovery_level)
    recovery_form.addRow("Default mode", recovery_mode)
    recovery_form.addRow(include_new)
    recovery_form.addRow(include_current)
    recovery_form.addRow("Recent-failure window", failure_days)
    recovery_form.addRow("Maximum Quick cards", max_quick)
    recovery_form.addRow("Maximum Standard cards", max_standard)
    recovery_form.addRow(ask_before)
    recovery_form.addRow("Deck naming pattern", deck_pattern)

    builder_form = form_tab("Study Builder")
    builder_intro = QLabel(
        "Recipes store only rules and selectors. Preview snippets and card fields are "
        "never written to Vellum's database or diagnostics."
    )
    builder_intro.setWordWrap(True)
    builder_shortcut_enabled = QCheckBox("Enable Study Builder shortcut")
    builder_shortcut_enabled.setChecked(config.study_builder.shortcut_enabled)
    builder_shortcut = QLineEdit(config.study_builder.shortcut)
    builder_limit = QSpinBox()
    builder_limit.setRange(1, 2_147_483_647)
    builder_limit.setValue(config.study_builder.default_limit)
    builder_limit.setSuffix(" cards")
    builder_state = QComboBox()
    _combo(
        builder_state,
        (
            ("Learn a topic · due + new", "due_new"),
            ("Review due", "due"),
            ("Learn new", "new"),
            ("Recent failures", "recent_failures"),
            ("All matching", "all"),
        ),
        config.study_builder.default_state_preset,
    )
    builder_order = QComboBox()
    _combo(
        builder_order,
        (
            ("Due first", "due"),
            ("Most at risk", "most_at_risk"),
            ("Most lapses", "most_lapses"),
            ("Oldest seen", "oldest_seen"),
            ("Order added", "added"),
            ("Random", "random"),
        ),
        config.study_builder.default_order,
    )
    builder_snippets = QCheckBox("Show ephemeral card snippets")
    builder_snippets.setChecked(config.study_builder.show_snippets)
    builder_anking = QCheckBox("Show detected AnKing facets")
    builder_anking.setChecked(config.study_builder.show_anking_facets)
    builder_form.addRow(builder_intro)
    builder_form.addRow(builder_shortcut_enabled)
    builder_form.addRow("Shortcut", builder_shortcut)
    builder_form.addRow("Default limit", builder_limit)
    builder_form.addRow("Default preset", builder_state)
    builder_form.addRow("Default order", builder_order)
    builder_form.addRow(builder_snippets)
    builder_form.addRow(builder_anking)

    time_form = form_tab("Time + HUD")
    presets = QLineEdit(", ".join(str(value) for value in config.time_machine.presets_minutes))
    adaptive = QCheckBox("Use adaptive review timing")
    adaptive.setChecked(config.time_machine.adaptive_timing)
    minimum_history = QSpinBox()
    minimum_history.setRange(3, 500)
    minimum_history.setValue(config.time_machine.minimum_history)
    fallback_widgets: dict[str, Any] = {}
    for name in ("new", "learning", "review", "relearning"):
        spin = QDoubleSpinBox()
        spin.setRange(1, 300)
        spin.setDecimals(1)
        spin.setSuffix(" sec/card")
        spin.setValue(float(getattr(config.time_machine.fallback_seconds, name)))
        fallback_widgets[name] = spin
        time_form.addRow(f"{name.title()} fallback", spin)
    end_behavior = QComboBox()
    _combo(end_behavior, (("Informational timer", "no_stop"), ("Soft notice", "soft_stop"), ("Finish prompt", "alert")), config.time_machine.end_behavior)
    time_shortcut_enabled = QCheckBox("Enable Study by Time shortcut")
    time_shortcut_enabled.setChecked(config.time_machine.shortcut_enabled)
    time_shortcut = QLineEdit(config.time_machine.shortcut)
    automatically_start_hud = QCheckBox("Automatically start the HUD")
    automatically_start_hud.setChecked(
        config.time_machine.automatically_start_hud
    )
    show_estimates_on_deck = QCheckBox("Show workload estimates on deck screens")
    show_estimates_on_deck.setChecked(
        config.time_machine.show_estimates_on_deck
    )
    hud_placement = QComboBox()
    _combo(hud_placement, (("Bottom left", "bottom_left"), ("Bottom center", "bottom_center"), ("Bottom right", "bottom_right"), ("Top", "top"), ("Hidden", "hidden")), config.hud.placement)
    hud_checks: dict[str, Any] = {}
    for field_name, label in (
        ("show_completed", "HUD: completed cards"),
        ("show_estimated_total", "HUD: estimated total"),
        ("show_elapsed", "HUD: elapsed time"),
        ("show_remaining_time", "HUD: remaining time"),
        ("show_eta", "HUD: estimated time to finish"),
        ("show_cards_per_minute", "HUD: cards per minute"),
        ("show_session_target", "HUD: session target"),
        ("show_progress_bar", "HUD: progress bar"),
    ):
        box = QCheckBox(label)
        box.setChecked(bool(getattr(config.hud, field_name)))
        hud_checks[field_name] = box
        time_form.addRow(box)
    time_form.addRow("Duration presets (minutes)", presets)
    time_form.addRow(adaptive)
    time_form.addRow("Minimum timing history", minimum_history)
    time_form.addRow("End behavior", end_behavior)
    time_form.addRow(time_shortcut_enabled)
    time_form.addRow("Shortcut", time_shortcut)
    time_form.addRow(automatically_start_hud)
    time_form.addRow(show_estimates_on_deck)
    time_form.addRow("HUD placement", hud_placement)

    continuity_form = form_tab("Resume + Home")
    checkpoints = QCheckBox("Enable session checkpoints")
    checkpoints.setChecked(config.resume.enable_checkpoints)
    checkpoint_seconds = QSpinBox()
    checkpoint_seconds.setRange(5, 3600)
    checkpoint_seconds.setValue(config.resume.checkpoint_seconds)
    checkpoint_seconds.setSuffix(" sec")
    detect_inactivity = QCheckBox("Detect inactivity")
    detect_inactivity.setChecked(config.resume.detect_inactivity)
    inactivity = QSpinBox()
    inactivity.setRange(60, 86400)
    inactivity.setValue(config.resume.inactivity_seconds)
    inactivity.setSuffix(" sec")
    show_launch = QCheckBox("Offer Resume on launch")
    show_launch.setChecked(config.resume.show_on_launch)
    show_home_resume = QCheckBox("Show Resume on Home Panel")
    show_home_resume.setChecked(config.resume.show_on_home)
    stale_days = QSpinBox()
    stale_days.setRange(1, 365)
    stale_days.setValue(config.resume.stale_after_days)
    history_days = QSpinBox()
    history_days.setRange(0, 3650)
    history_days.setSpecialValueText("Forever")
    history_days.setValue(config.resume.history_days)
    max_sessions = QSpinBox()
    max_sessions.setRange(10, 10000)
    max_sessions.setValue(config.resume.maximum_sessions)
    ramp_launch = QCheckBox("Offer Return Ramp after an absence")
    ramp_launch.setChecked(config.return_ramp.show_on_launch)
    ramp_days = QSpinBox()
    ramp_days.setRange(1, MAX_ABSENCE_DAYS)
    ramp_days.setValue(config.return_ramp.absence_days)
    ramp_days.setSuffix(" days")
    ramp_suggestions = QSpinBox()
    ramp_suggestions.setRange(1, 5)
    ramp_suggestions.setValue(config.return_ramp.suggestion_count)
    home_checks: dict[str, Any] = {}
    for field_name, label in (
        ("show_greeting", "Home: greeting"),
        ("show_continue", "Home: Continue block"),
        ("show_time_machine", "Home: Study by Time block"),
        ("show_study_builder", "Home: Study Builder block"),
        ("show_weak_topics", "Home: topics needing attention"),
        ("show_estimated_workload", "Home: estimated workload"),
    ):
        box = QCheckBox(label)
        box.setChecked(bool(getattr(config.home, field_name)))
        home_checks[field_name] = box
        continuity_form.addRow(box)
    continuity_form.addRow(checkpoints)
    continuity_form.addRow("Checkpoint interval", checkpoint_seconds)
    continuity_form.addRow(detect_inactivity)
    continuity_form.addRow("Inactivity threshold", inactivity)
    continuity_form.addRow(show_launch)
    continuity_form.addRow(show_home_resume)
    continuity_form.addRow("Stale after", stale_days)
    continuity_form.addRow("Keep history", history_days)
    continuity_form.addRow("Maximum sessions", max_sessions)
    continuity_form.addRow(ramp_launch)
    continuity_form.addRow("Return Ramp absence threshold", ramp_days)
    continuity_form.addRow("Suggested session sizes", ramp_suggestions)
    debrief_card = QCheckBox("Show a completion card for generated sessions")
    debrief_card.setChecked(config.debrief.show_completion_card)
    debrief_normal = QCheckBox("Keep quiet summaries of regular study sessions")
    debrief_normal.setChecked(config.debrief.include_normal_sessions)
    debrief_handoff = QCheckBox("Enable one-line session handoffs")
    debrief_handoff.setChecked(config.debrief.handoff_enabled)
    continuity_form.addRow(debrief_card)
    continuity_form.addRow(debrief_normal)
    continuity_form.addRow(debrief_handoff)

    memory_form = form_tab("Memory")
    backtrack_shortcut_enabled = QCheckBox("Enable Backtrack shortcut")
    backtrack_shortcut_enabled.setChecked(config.backtrack.shortcut_enabled)
    backtrack_shortcut = QLineEdit(config.backtrack.shortcut)
    backtrack_limit = QSpinBox()
    backtrack_limit.setRange(2, 250)
    backtrack_limit.setValue(config.backtrack.history_limit)
    mind_shortcut_enabled = QCheckBox("Enable Mind Notes shortcut")
    mind_shortcut_enabled.setChecked(config.mind_notes.shortcut_enabled)
    mind_shortcut = QLineEdit(config.mind_notes.shortcut)
    mind_resurface = QCheckBox("Resurface active notes with their topic")
    mind_resurface.setChecked(config.mind_notes.resurface)
    mind_limit = QSpinBox()
    mind_limit.setRange(1, 10)
    mind_limit.setValue(config.mind_notes.maximum_active_per_topic)
    memory_note = QLabel(
        "Backtrack is read-only and lives only for the current Anki run. Mind Notes "
        "are stored locally in Vellum's private database; card text is never copied."
    )
    memory_note.setWordWrap(True)
    memory_form.addRow(memory_note)
    memory_form.addRow(backtrack_shortcut_enabled)
    memory_form.addRow("Backtrack shortcut", backtrack_shortcut)
    memory_form.addRow("Cards remembered this run", backtrack_limit)
    memory_form.addRow(mind_shortcut_enabled)
    memory_form.addRow("Mind Notes shortcut", mind_shortcut)
    memory_form.addRow(mind_resurface)
    memory_form.addRow("Notes shown per topic", mind_limit)

    parsing_form = form_tab("Topic Parsing")
    roots = QPlainTextEdit("\n".join(config.topic_parsing.preferred_roots))
    roots.setMaximumHeight(110)
    ignored_roots = QPlainTextEdit("\n".join(config.topic_parsing.ignored_roots))
    ignored_roots.setMaximumHeight(80)
    ignored_segments = QPlainTextEdit("\n".join(config.topic_parsing.ignored_segments))
    ignored_segments.setMaximumHeight(70)
    renames = QPlainTextEdit("\n".join(f"{key} = {value}" for key, value in config.topic_parsing.renamed_segments.items()))
    renames.setMaximumHeight(80)
    source_badges = QPlainTextEdit(
        "\n".join(
            f"{key} = {value}"
            for key, value in config.topic_parsing.source_badges.items()
        )
    )
    source_badges.setMaximumHeight(90)
    depth = QSpinBox()
    depth.setRange(1, 20)
    depth.setValue(config.topic_parsing.maximum_depth)
    anking = QCheckBox("Enable version-tolerant AnKing adapter")
    anking.setChecked(config.topic_parsing.anking_adapter)
    generic = QCheckBox("Allow generic hierarchical tags")
    generic.setChecked(config.topic_parsing.generic_fallback)
    preview_label = QLabel("Open a reviewer card to preview its current parsing.")
    preview_label.setWordWrap(True)
    preview_button = QPushButton("Preview current card")

    def preview() -> None:
        card = getattr(getattr(parent, "reviewer", None), "card", None)
        if card is None:
            preview_label.setText("No current reviewer card.")
            return
        from ..topics.parser import TopicParser

        draft = TopicParsingConfig(
            preferred_roots=_lines(roots)
            or config.topic_parsing.preferred_roots,
            ignored_roots=_lines(ignored_roots),
            ignored_segments=_lines(ignored_segments),
            renamed_segments=_key_value_lines(renames),
            source_badges=_key_value_lines(source_badges),
            maximum_depth=depth.value(),
            anking_adapter=anking.isChecked(),
            generic_fallback=generic.isChecked(),
        )
        parsed = TopicParser(draft).parse(
            tuple(str(tag) for tag in card.note().tags)
        )
        preview_label.setText(
            f"Raw tag: {parsed.raw_tag or 'None'}\nParsed: "
            + (" → ".join(parsed.path) if parsed.found else "No topic hierarchy found")
        )

    qconnect(preview_button.clicked, preview)
    parsing_form.addRow("Preferred roots, highest priority first", roots)
    parsing_form.addRow("Ignored roots", ignored_roots)
    parsing_form.addRow("Ignored segments", ignored_segments)
    parsing_form.addRow("Renames (segment = label)", renames)
    parsing_form.addRow("Source badges (root = label)", source_badges)
    parsing_form.addRow("Maximum depth", depth)
    parsing_form.addRow(anking)
    parsing_form.addRow(generic)
    parsing_form.addRow(preview_button, preview_label)

    data_page = QWidget()
    data_layout = QVBoxLayout(data_page)
    data_layout.addWidget(QLabel("These controls affect only Vellum's separate local database."))
    rebuild_cache = QPushButton("Rebuild topic cache")
    clear_sessions = QPushButton("Clear session history")
    clear_generated = QPushButton("Clear generated deck history")
    clear_builder = QPushButton("Clear Study Builder recipes and recent searches")
    clear_timing = QPushButton("Clear timing history")
    clear_mind_notes = QPushButton("Clear Mind Notes")
    reset_health = QPushButton("Reset Topic Health and recent topics")
    export_diagnostics = QPushButton("Export redacted diagnostics…")
    reset_all = QPushButton("Reset all Vellum data…")
    for button in (
        rebuild_cache,
        clear_sessions,
        clear_generated,
        clear_builder,
        clear_timing,
        clear_mind_notes,
        reset_health,
        export_diagnostics,
        reset_all,
    ):
        data_layout.addWidget(button)
    reset_all.setStyleSheet("color: #b3261e;")
    data_layout.addStretch(1)
    tabs.addTab(data_page, "Data")

    def rebuild() -> None:
        app.services.topics.invalidate()
        tooltip("Topic cache cleared; it will rebuild lazily.", parent=dialog)

    qconnect(rebuild_cache.clicked, rebuild)

    def clear_tables(title: str, tables: tuple[str, ...]) -> None:
        if reset_would_break_active_session(app, tables):
            showWarning(
                "Finish the current Vellum session before clearing its history. "
                "The retained session and generated-deck records are required to "
                "return cards safely and offer truthful Resume behavior.",
                parent=dialog,
            )
            return
        if not askUser(f"{title}? This cannot be undone.", parent=dialog):
            return
        clear_vellum_data(app.services.database, tables)
        if "sessions" in tables:
            app.services.sessions.current = None
        app.services.timing.reset_session_blend()
        tooltip(f"{title} complete", parent=dialog)

    qconnect(
        clear_sessions.clicked,
        lambda: clear_tables(
            "Clear session history",
            (
                "session_mind_note_events",
                "session_debriefs",
                "session_cards",
                "sessions",
            ),
        ),
    )
    qconnect(
        clear_generated.clicked,
        lambda: clear_tables(
            "Clear generated deck history",
            (
                "generated_deck_card_answers",
                "generated_deck_cards",
                "generated_deck_history",
            ),
        ),
    )
    qconnect(
        clear_builder.clicked,
        lambda: clear_tables(
            "Clear Study Builder recipes and recent searches",
            ("study_builder_recent", "study_recipes"),
        ),
    )
    qconnect(clear_timing.clicked, lambda: clear_tables("Clear timing history", ("timing_samples", "timing_stats")))
    def clear_notes() -> None:
        if not askUser("Clear Mind Notes? This cannot be undone.", parent=dialog):
            return
        clear_mind_note_data(app.services.database)
        tooltip("Clear Mind Notes complete", parent=dialog)

    qconnect(clear_mind_notes.clicked, clear_notes)
    qconnect(
        reset_health.clicked,
        lambda: clear_tables(
            "Reset Topic Health and recent topics",
            ("topic_path_cache", "topic_cache"),
        ),
    )
    qconnect(reset_all.clicked, lambda: clear_tables("Reset all Vellum data", RESET_TABLES))

    def export() -> None:
        default = str(Path.home() / "Desktop" / "vellum-diagnostics.json")
        path, _filter = QFileDialog.getSaveFileName(dialog, "Export Vellum Diagnostics", default, "JSON (*.json)")
        if not path:
            return
        try:
            try:
                from anki.buildinfo import version as anki_version  # type: ignore[import-not-found]
            except Exception:
                anki_version = "unknown"
            payload = build_diagnostics(
                config=app.config,
                database=app.services.database,
                log_path=app.services.database.path.parent / "vellum.log",
                anki_version=str(anki_version),
            )
            write_diagnostics(Path(path), payload)
            showInfo("Diagnostics exported without card text, note fields, or tag names.", parent=dialog)
        except Exception as error:
            showWarning(f"Diagnostics export failed: {error}", parent=dialog)

    qconnect(export_diagnostics.clicked, export)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    outer.addWidget(buttons)

    def save() -> None:
        preset_values: list[int] = []
        for value in presets.text().split(","):
            try:
                number = int(value.strip())
            except ValueError:
                continue
            if 1 <= number <= 480 and number not in preset_values:
                preset_values.append(number)
        rename_map = _key_value_lines(renames)
        source_badge_map = _key_value_lines(source_badges)
        pattern = deck_pattern.text().strip()
        if "{topic}" not in pattern:
            showWarning("Recovery deck naming pattern must contain {topic}.", parent=dialog)
            return
        flags = ModuleFlags(**{name: box.isChecked() for name, box in module_boxes.items()})
        fallback = FallbackSeconds(**{name: widget.value() for name, widget in fallback_widgets.items()})
        updated = replace(
            config,
            enabled=enabled.isChecked(),
            modules=flags,
            general=replace(config.general, show_menu=show_menu.isChecked(), keyboard_shortcuts=keyboard_shortcuts.isChecked(), animations=animations.isChecked(), reduced_motion=reduced.isChecked(), debug_logging=debug.isChecked(), theme=theme.currentData()),
            context=replace(config.context, side=context_side.currentData(), default_state=context_state.currentData(), width=context_width.value(), auto_collapse_on_new_card=auto_collapse.isChecked(), pinned=context_pinned.isChecked(), shortcut_enabled=context_shortcut_enabled.isChecked(), shortcut=context_shortcut.text().strip() or "C", collapse_shortcut=collapse_shortcut.text().strip() or "Escape", **{name: box.isChecked() for name, box in context_checks.items()}),
            recovery=replace(config.recovery, shortcut_enabled=recovery_shortcut_enabled.isChecked(), shortcut=recovery_shortcut.text().strip() or "Shift+C", default_level=recovery_level.currentData(), default_mode=recovery_mode.currentData(), include_new=include_new.isChecked(), include_current=include_current.isChecked(), recent_failure_days=failure_days.value(), max_quick=max_quick.value(), max_standard=max_standard.value(), ask_before_create=ask_before.isChecked(), deck_name_pattern=pattern),
            study_builder=replace(config.study_builder, shortcut_enabled=builder_shortcut_enabled.isChecked(), shortcut=builder_shortcut.text().strip() or "Ctrl+Shift+B", default_limit=builder_limit.value(), default_state_preset=builder_state.currentData(), default_order=builder_order.currentData(), show_snippets=builder_snippets.isChecked(), show_anking_facets=builder_anking.isChecked()),
            time_machine=replace(config.time_machine, presets_minutes=tuple(preset_values) or config.time_machine.presets_minutes, adaptive_timing=adaptive.isChecked(), minimum_history=minimum_history.value(), end_behavior=end_behavior.currentData(), fallback_seconds=fallback, shortcut_enabled=time_shortcut_enabled.isChecked(), shortcut=time_shortcut.text().strip() or "Ctrl+Shift+T", automatically_start_hud=automatically_start_hud.isChecked(), show_estimates_on_deck=show_estimates_on_deck.isChecked()),
            hud=replace(config.hud, placement=hud_placement.currentData(), **{name: box.isChecked() for name, box in hud_checks.items()}),
            resume=replace(config.resume, enable_checkpoints=checkpoints.isChecked(), checkpoint_seconds=checkpoint_seconds.value(), detect_inactivity=detect_inactivity.isChecked(), inactivity_seconds=inactivity.value(), show_on_launch=show_launch.isChecked(), show_on_home=show_home_resume.isChecked(), stale_after_days=stale_days.value(), history_days=history_days.value(), maximum_sessions=max_sessions.value()),
            return_ramp=replace(config.return_ramp, show_on_launch=ramp_launch.isChecked(), absence_days=ramp_days.value(), suggestion_count=ramp_suggestions.value()),
            backtrack=replace(config.backtrack, shortcut_enabled=backtrack_shortcut_enabled.isChecked(), shortcut=backtrack_shortcut.text().strip() or "Alt+B", history_limit=backtrack_limit.value()),
            mind_notes=replace(config.mind_notes, shortcut_enabled=mind_shortcut_enabled.isChecked(), shortcut=mind_shortcut.text().strip() or "Alt+M", resurface=mind_resurface.isChecked(), maximum_active_per_topic=mind_limit.value()),
            debrief=replace(config.debrief, show_completion_card=debrief_card.isChecked(), include_normal_sessions=debrief_normal.isChecked(), handoff_enabled=debrief_handoff.isChecked()),
            home=replace(config.home, **{name: box.isChecked() for name, box in home_checks.items()}),
            topic_parsing=replace(config.topic_parsing, preferred_roots=_lines(roots) or config.topic_parsing.preferred_roots, ignored_roots=_lines(ignored_roots), ignored_segments=_lines(ignored_segments), renamed_segments=rename_map, source_badges=source_badge_map, maximum_depth=depth.value(), anking_adapter=anking.isChecked(), generic_fallback=generic.isChecked()),
        )
        app.apply_config(updated)
        dialog.accept()

    qconnect(buttons.accepted, save)
    qconnect(buttons.rejected, dialog.reject)
    if initial_tab is not None:
        for index in range(tabs.count()):
            if tabs.tabText(index) == initial_tab:
                tabs.setCurrentIndex(index)
                break
    dialog.exec()
