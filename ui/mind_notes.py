"""Native capture and history surfaces for topic-linked Mind Notes."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Callable

from .theme import apply_secondary_text


def show_mind_note_editor(
    parent: Any,
    *,
    topic_label: str,
    topic_path: tuple[str, ...],
    on_save: Callable[[str], None],
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QLabel,
        QPlainTextEdit,
        QTextCursor,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Add Vellum Mind Note")
    dialog.setMinimumWidth(590)
    layout = QVBoxLayout(dialog)
    eyebrow = QLabel("REMEMBER THIS WHEN THE TOPIC RETURNS")
    eyebrow.setStyleSheet(
        "font-size: 11px; font-weight: 700; letter-spacing: 1.4px;"
    )
    apply_secondary_text(eyebrow)
    layout.addWidget(eyebrow)
    title = QLabel(topic_label)
    title.setStyleSheet("font-size: 23px; font-weight: 650;")
    title.setWordWrap(True)
    layout.addWidget(title)
    path = QLabel(" → ".join(topic_path))
    path.setWordWrap(True)
    apply_secondary_text(path)
    layout.addWidget(path)
    editor = QPlainTextEdit()
    editor.setPlaceholderText(
        "What do you want your future self to remember or resolve?"
    )
    editor.setMaximumBlockCount(40)
    editor.setMinimumHeight(150)
    layout.addWidget(editor)
    count = QLabel("0 / 2000")
    apply_secondary_text(count)
    layout.addWidget(count)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save
        | QDialogButtonBox.StandardButton.Cancel
    )
    save = buttons.button(QDialogButtonBox.StandardButton.Save)
    save.setEnabled(False)

    def changed() -> None:
        text = editor.toPlainText()
        if len(text) > 2_000:
            editor.blockSignals(True)
            editor.setPlainText(text[:2_000])
            editor.moveCursor(QTextCursor.MoveOperation.End)
            editor.blockSignals(False)
            text = editor.toPlainText()
        count.setText(f"{len(text)} / 2000")
        save.setEnabled(bool(text.strip()))

    def accepted() -> None:
        body = editor.toPlainText().strip()
        if not body:
            return
        dialog.accept()
        on_save(body)

    qconnect(editor.textChanged, changed)
    qconnect(buttons.accepted, accepted)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    editor.setFocus()
    dialog.exec()


def show_mind_note_history(parent: Any, repository: Any) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        qconnect,
    )

    notes = repository.recent(limit=300)
    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Mind Notes")
    dialog.resize(820, 560)
    layout = QVBoxLayout(dialog)
    title = QLabel("Mind Notes")
    title.setStyleSheet("font-size: 22px; font-weight: 650;")
    layout.addWidget(title)
    subtitle = QLabel(
        "Local notes linked to topic identity. Card text is never copied into this history."
    )
    subtitle.setWordWrap(True)
    apply_secondary_text(subtitle)
    layout.addWidget(subtitle)
    content = QHBoxLayout()
    listing = QListWidget()
    detail = QTextBrowser()
    content.addWidget(listing, 1)
    content.addWidget(detail, 2)
    layout.addLayout(content, 1)
    for note in notes:
        status = "Resolved" if note.resolved_at is not None else "Active"
        when = datetime.fromtimestamp(note.created_at).astimezone().strftime("%Y-%m-%d")
        listing.addItem(f"{note.topic_label}\n{when} · {status}")

    def selected(row: int) -> None:
        if not 0 <= row < len(notes):
            detail.clear()
            return
        note = notes[row]
        status = "Resolved" if note.resolved_at is not None else "Active"
        detail.setHtml(
            f"<h2>{escape(note.topic_label)}</h2>"
            f"<p>{escape(' → '.join(note.topic_path))}</p>"
            f"<p><b>{status}</b> · "
            f"{escape(datetime.fromtimestamp(note.created_at).astimezone().isoformat())}</p>"
            f"<blockquote>{escape(note.body).replace(chr(10), '<br>')}</blockquote>"
        )

    qconnect(listing.currentRowChanged, selected)
    if notes:
        listing.setCurrentRow(0)
    else:
        detail.setHtml("<h2>No Mind Notes yet</h2>")
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
