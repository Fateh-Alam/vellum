"""Focused Resume decision dialog."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..sessions.resume import ResumeAssessment, ResumeMode


def _age_copy(seconds: int) -> str:
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return f"{minutes} min ago"
    if seconds < 86_400:
        return f"{seconds // 3600} hr ago"
    return f"{seconds // 86_400} days ago"


def show_resume_dialog(
    parent: Any,
    assessment: ResumeAssessment,
    on_resume: Callable[[], None],
    on_abandon: Callable[[], None],
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QLabel,
        QPushButton,
        QVBoxLayout,
        qconnect,
    )

    session = assessment.session
    dialog = QDialog(parent)
    dialog.setWindowTitle("Resume with Vellum")
    dialog.setMinimumWidth(390)
    layout = QVBoxLayout(dialog)

    eyebrow = QLabel("CONTINUE")
    eyebrow.setStyleSheet("font-size: 10px; letter-spacing: 2px;")
    layout.addWidget(eyebrow)
    title = QLabel(session.deck_name or "Previous study session")
    title.setStyleSheet("font-size: 20px; font-weight: 650;")
    title.setWordWrap(True)
    layout.addWidget(title)

    parts = [f"{session.reviewed_count} reviewed", _age_copy(assessment.age_seconds)]
    if assessment.expected_remaining is not None:
        parts.insert(1, f"{assessment.expected_remaining} previously remaining")
    summary = QLabel(" · ".join(parts))
    summary.setWordWrap(True)
    layout.addWidget(summary)

    if assessment.newly_due:
        changed = QLabel(f"{assessment.newly_due} additional cards are now due.")
        changed.setStyleSheet("font-weight: 600;")
        layout.addWidget(changed)

    explanation = QLabel(assessment.explanation)
    explanation.setWordWrap(True)
    explanation.setStyleSheet("margin-top: 6px;")
    layout.addWidget(explanation)

    can_resume = session.deck_id is not None
    resume_label = (
        "Resume session"
        if assessment.mode is ResumeMode.EXACT
        else "Resume current context"
    )
    if not can_resume:
        resume_label = "Original deck unavailable"
    resume_button = QPushButton(resume_label)
    resume_button.setDefault(True)
    resume_button.setEnabled(can_resume)
    abandon_button = QPushButton("Abandon session")
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    buttons.addButton(abandon_button, QDialogButtonBox.ButtonRole.DestructiveRole)
    buttons.addButton(resume_button, QDialogButtonBox.ButtonRole.AcceptRole)
    layout.addWidget(buttons)

    def resume() -> None:
        dialog.accept()
        on_resume()

    def abandon() -> None:
        dialog.accept()
        on_abandon()

    qconnect(resume_button.clicked, resume)
    qconnect(abandon_button.clicked, abandon)
    qconnect(buttons.rejected, dialog.reject)
    dialog.exec()
