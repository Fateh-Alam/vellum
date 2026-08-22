"""Time Machine duration and estimate dialogs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..anki.time_machine import TimeMachineDeckChoice
from ..timing.models import SessionEstimate, TimingBucket


def show_duration_dialog(parent: Any, presets: tuple[int, ...], on_selected: Callable[[int], None]) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Time Machine")
    dialog.setMinimumWidth(520)
    layout = QVBoxLayout(dialog)
    title = QLabel("How much time do you have?")
    title.setStyleSheet("font-size: 19px; font-weight: 650;")
    layout.addWidget(title)
    intro = QLabel(
        "Vellum estimates every normal deck, then uses an Anki-native temporary "
        "filtered deck to study them together."
    )
    intro.setWordWrap(True)
    layout.addWidget(intro)
    row = QHBoxLayout()
    layout.addLayout(row)

    def choose(minutes: int) -> None:
        dialog.accept()
        on_selected(minutes)

    for minutes in presets:
        button = QPushButton(f"{minutes} min")
        qconnect(button.clicked, lambda _checked=False, value=minutes: choose(value))
        row.addWidget(button)

    custom = QSpinBox()
    custom.setRange(1, 480)
    custom.setValue(presets[0] if presets else 20)
    custom.setSuffix(" min")
    custom_row = QHBoxLayout()
    custom_row.addWidget(QLabel("Custom duration"))
    custom_row.addStretch(1)
    custom_row.addWidget(custom)
    layout.addLayout(custom_row)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if ok is not None:
        ok.setText("Estimate Session")
        ok.setDefault(True)
    qconnect(buttons.accepted, lambda: choose(custom.value()))
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()


def show_deck_selection_dialog(
    parent: Any,
    minutes: int,
    choices: tuple[TimeMachineDeckChoice, ...],
    on_selected: Callable[[tuple[int, ...]], None],
) -> None:
    """Choose disjoint deck groups for one Time Machine run."""

    from aqt.qt import (  # type: ignore[import-not-found]
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Choose Time Machine Decks")
    dialog.setMinimumSize(560, 430)
    layout = QVBoxLayout(dialog)
    title = QLabel(f"Choose decks for {minutes} minutes")
    title.setStyleSheet("font-size: 19px; font-weight: 650;")
    layout.addWidget(title)
    intro = QLabel(
        "All available deck groups are selected by default. Each parent deck "
        "includes its subdecks; filtered decks are left untouched."
    )
    intro.setWordWrap(True)
    layout.addWidget(intro)

    controls = QHBoxLayout()
    select_all = QPushButton("Select All")
    clear = QPushButton("Clear")
    controls.addWidget(select_all)
    controls.addWidget(clear)
    controls.addStretch(1)
    layout.addLayout(controls)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    list_widget = QWidget()
    list_layout = QVBoxLayout(list_widget)
    checkboxes: dict[int, Any] = {}
    for choice in choices:
        suffix = (
            f"{choice.available_cards} available · {choice.new_cards} new · "
            f"{choice.learning_cards} learning · {choice.review_cards} review"
            if choice.available_cards
            else "No cards available now"
        )
        checkbox = QCheckBox(f"{choice.deck_name}\n{suffix}")
        checkbox.setChecked(choice.available_cards > 0)
        checkbox.setEnabled(choice.available_cards > 0)
        checkbox.setStyleSheet("QCheckBox { padding: 7px 3px; }")
        checkboxes[choice.deck_id] = checkbox
        list_layout.addWidget(checkbox)
    list_layout.addStretch(1)
    scroll.setWidget(list_widget)
    layout.addWidget(scroll, 1)

    status = QLabel()
    status.setWordWrap(True)
    layout.addWidget(status)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    estimate = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if estimate is not None:
        estimate.setText("Estimate Session")
        estimate.setDefault(True)
    layout.addWidget(buttons)

    def selected_ids() -> tuple[int, ...]:
        return tuple(
            choice.deck_id
            for choice in choices
            if choice.available_cards > 0 and checkboxes[choice.deck_id].isChecked()
        )

    def refresh() -> None:
        selected = selected_ids()
        cards = sum(
            choice.available_cards for choice in choices if choice.deck_id in selected
        )
        noun = "deck" if len(selected) == 1 else "decks"
        status.setText(f"{len(selected)} {noun} selected · {cards} cards available")
        if estimate is not None:
            estimate.setEnabled(bool(selected))

    def set_all(checked: bool) -> None:
        for choice in choices:
            if choice.available_cards > 0:
                checkboxes[choice.deck_id].setChecked(checked)
        refresh()

    for checkbox in checkboxes.values():
        qconnect(checkbox.toggled, lambda _checked: refresh())
    qconnect(select_all.clicked, lambda: set_all(True))
    qconnect(clear.clicked, lambda: set_all(False))

    def accept() -> None:
        selected = selected_ids()
        if not selected:
            refresh()
            return
        dialog.accept()
        on_selected(selected)

    qconnect(buttons.accepted, accept)
    qconnect(buttons.rejected, dialog.reject)
    refresh()
    dialog.exec()


def show_estimate_dialog(
    parent: Any,
    minutes: int,
    estimate: SessionEstimate,
    available_cards: int | None,
    on_start: Callable[[], None],
    *,
    scope_label: str | None = None,
    active_decks: int | None = None,
    truncated: bool = False,
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QLabel,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Time Machine Estimate")
    layout = QVBoxLayout(dialog)
    heading = QLabel(f"{minutes}-minute session")
    heading.setStyleSheet("font-size: 20px; font-weight: 650;")
    layout.addWidget(heading)
    if scope_label:
        scope = scope_label
        if active_decks is not None:
            noun = "deck" if active_decks == 1 else "decks"
            scope += f" · {active_decks} active {noun}"
        layout.addWidget(QLabel(scope))
    if available_cards is None:
        noun = "card" if estimate.expected_cards == 1 else "cards"
        capacity = QLabel(
            f"About {estimate.expected_cards} {noun} at the static fallback rate. "
            "The current queue count could not be verified."
        )
        capacity.setWordWrap(True)
        layout.addWidget(capacity)
    else:
        available_noun = "card" if available_cards == 1 else "cards"
        layout.addWidget(
            QLabel(
                f"About {estimate.expected_cards} of {available_cards} available "
                f"{available_noun}"
            )
        )
    labels = {
        TimingBucket.NEW: "New",
        TimingBucket.LEARNING: "Learning",
        TimingBucket.REVIEW: "Review",
        TimingBucket.RELEARNING: "Relearning",
    }
    breakdown = " · ".join(
        f"{count} {labels[bucket]}" for bucket, count in estimate.per_bucket.items()
    )
    if breakdown:
        detail = QLabel(breakdown)
        detail.setWordWrap(True)
        layout.addWidget(detail)
    if estimate.fallback_buckets:
        learning = QLabel(
            "Vellum is learning your review speed. Using your configured "
            "default estimates for now."
        )
        learning.setWordWrap(True)
        layout.addWidget(learning)
    if truncated:
        capped = QLabel(
            "This collection exceeds Vellum's 100,000-card safety cap. The "
            "estimate and temporary session use the first 100,000 cards."
        )
        capped.setWordWrap(True)
        layout.addWidget(capped)
    safety = QLabel(
        "Starting creates a temporary Vellum filtered deck. Cards remain linked "
        "to their home decks, and answers use normal Anki scheduling."
    )
    safety.setWordWrap(True)
    layout.addWidget(safety)
    note = QLabel(
        f"The filtered deck will contain only these {estimate.expected_cards} "
        "planned cards. The session ends when that bounded deck is exhausted; "
        "the clock never adds more cards."
    )
    note.setWordWrap(True)
    layout.addWidget(note)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    start_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
    start_button.setText("Start Session")
    start_button.setEnabled(estimate.expected_cards > 0)

    def start() -> None:
        if estimate.expected_cards <= 0:
            return
        dialog.accept()
        on_start()

    qconnect(buttons.accepted, start)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
