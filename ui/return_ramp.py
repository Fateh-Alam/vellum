"""Calm native re-entry screen after a configurable absence."""

from __future__ import annotations

from typing import Any, Callable

from ..continuity.return_ramp import ReturnRampWorkload
from .theme import apply_secondary_text


def show_return_ramp_dialog(
    parent: Any,
    workload: ReturnRampWorkload,
    *,
    resume_label: str | None,
    generated_session_waiting: bool,
    can_start_time_machine: bool,
    on_resume: Callable[[], None],
    on_start: Callable[[int], None],
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Return Ramp")
    dialog.setMinimumWidth(620)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 26, 28, 22)
    layout.setSpacing(14)

    eyebrow = QLabel("RETURN RAMP")
    eyebrow.setStyleSheet(
        "font-size: 11px; font-weight: 700; letter-spacing: 1.5px;"
    )
    apply_secondary_text(eyebrow)
    layout.addWidget(eyebrow)
    title = QLabel("Welcome back. Start smaller than the backlog.")
    title.setStyleSheet("font-size: 25px; font-weight: 650;")
    title.setWordWrap(True)
    layout.addWidget(title)
    absence_copy = (
        f"You have been away for about {workload.absence_days} "
        f"{'day' if workload.absence_days == 1 else 'days'}. "
        if workload.absence_days > 0
        else "Here is a calm view of the workload available now. "
    )
    away = QLabel(
        absence_copy
        + "Nothing here changes Anki's scheduler until you choose a session."
    )
    away.setWordWrap(True)
    apply_secondary_text(away)
    layout.addWidget(away)

    metrics = QFrame()
    metrics.setFrameShape(QFrame.Shape.StyledPanel)
    grid = QGridLayout(metrics)
    values = (
        (str(workload.available_cards), "Available now"),
        (str(workload.review_cards), "Review"),
        (str(workload.learning_cards), "Learning"),
        (str(workload.new_cards), "New"),
    )
    for index, (value, label) in enumerate(values):
        number = QLabel(value)
        number.setStyleSheet("font-size: 22px; font-weight: 650;")
        caption = QLabel(label)
        apply_secondary_text(caption)
        grid.addWidget(number, 0, index)
        grid.addWidget(caption, 1, index)
    layout.addWidget(metrics)

    estimate = QLabel(
        f"Across {workload.active_decks} active deck "
        f"{'group' if workload.active_decks == 1 else 'groups'}, the full "
        f"available workload is about {workload.estimated_minutes} minutes."
    )
    estimate.setWordWrap(True)
    layout.addWidget(estimate)

    if resume_label:
        resume_frame = QFrame()
        resume_frame.setFrameShape(QFrame.Shape.StyledPanel)
        resume_layout = QHBoxLayout(resume_frame)
        resume_copy = QLabel("Continue where you stopped\n" + resume_label)
        resume_copy.setStyleSheet("font-weight: 600;")
        resume_button = QPushButton("Resume →")
        qconnect(
            resume_button.clicked,
            lambda: (dialog.accept(), on_resume()),
        )
        resume_layout.addWidget(resume_copy, 1)
        resume_layout.addWidget(resume_button)
        layout.addWidget(resume_frame)

    prompt = QLabel(
        "Suggested bounded sessions"
        if not generated_session_waiting
        else "Finish or resume the waiting Vellum deck before starting another."
    )
    prompt.setStyleSheet("font-weight: 650;")
    prompt.setWordWrap(True)
    layout.addWidget(prompt)
    choices = QHBoxLayout()
    for suggestion in workload.suggestions:
        button = QPushButton(
            f"{suggestion.minutes} min\n~{suggestion.expected_cards} cards"
        )
        button.setMinimumHeight(54)
        button.setEnabled(
            can_start_time_machine and not generated_session_waiting
        )
        qconnect(
            button.clicked,
            lambda _checked=False, minutes=suggestion.minutes: (
                dialog.accept(),
                on_start(minutes),
            ),
        )
        choices.addWidget(button)
    layout.addLayout(choices)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
