"""Read-only prior-card and prior-topic viewer outside Anki Browser."""

from __future__ import annotations

from datetime import datetime
from html import escape
import re
from typing import Any

from ..continuity.backtrack import BacktrackEntry
from .theme import apply_secondary_text


def _shown_time(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )


def show_backtrack_dialog(
    parent: Any,
    mw: Any,
    previous_card: BacktrackEntry,
    previous_topic: BacktrackEntry,
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QLabel,
        QTabWidget,
        QVBoxLayout,
        QWidget,
        qconnect,
    )
    from aqt.webview import (  # type: ignore[import-not-found]
        AnkiWebView,
        AnkiWebViewKind,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Backtrack")
    dialog.resize(880, 680)
    layout = QVBoxLayout(dialog)
    heading = QLabel("Backtrack")
    heading.setStyleSheet("font-size: 22px; font-weight: 650;")
    layout.addWidget(heading)
    boundary = QLabel(
        "Read-only recall. Viewing this card does not answer it, undo it, or "
        "change Anki scheduling."
    )
    boundary.setWordWrap(True)
    apply_secondary_text(boundary)
    layout.addWidget(boundary)

    tabs = QTabWidget()
    layout.addWidget(tabs, 1)
    card_page = QWidget()
    card_layout = QVBoxLayout(card_page)
    card_meta = QLabel(
        f"Previous card · {escape(previous_card.deck_name or 'Unknown deck')} · "
        f"seen {_shown_time(previous_card.shown_at)}"
    )
    card_meta.setWordWrap(True)
    card_layout.addWidget(card_meta)
    web = AnkiWebView(card_page, kind=AnkiWebViewKind.PREVIEWER)
    card_layout.addWidget(web, 1)
    tabs.addTab(card_page, "Previous card")

    try:
        card = mw.col.get_card(previous_card.card_id)
        question = re.sub(
            r"\[\[type:[^]]+\]\]", "", mw.prepare_card_text_for_display(card.question())
        )
        answer = re.sub(
            r"\[\[type:[^]]+\]\]", "", mw.prepare_card_text_for_display(card.answer())
        )
        model_css = str(card.note_type().get("css", ""))
        body = (
            '<main class="vellum-backtrack-card">'
            '<div class="vellum-backtrack-label">QUESTION</div>'
            f'<section class="card">{question}</section>'
            '<hr><div class="vellum-backtrack-label">ANSWER</div>'
            f'<section class="card">{answer}</section></main>'
        )
        head = (
            f"<style>{model_css}</style>"
            "<style>.vellum-backtrack-card{max-width:900px;margin:0 auto;"
            "padding:22px}.vellum-backtrack-label{font:700 10px/1.3 "
            "system-ui;letter-spacing:.14em;opacity:.72;margin:4px 0 14px}"
            ".vellum-backtrack-card hr{border:0;border-top:1px solid "
            "rgba(127,127,127,.25);margin:28px 0}</style>"
        )
        web.stdHtml(body, css=["css/reviewer.css"], head=head, context=dialog)
    except Exception as error:
        web.stdHtml(
            "<p>This previous card is no longer available.</p>"
            f"<p>{escape(str(error))}</p>",
            context=dialog,
        )

    topic_page = QWidget()
    topic_layout = QVBoxLayout(topic_page)
    topic_eyebrow = QLabel("PREVIOUS TOPIC CONTEXT")
    topic_eyebrow.setStyleSheet(
        "font-size: 11px; font-weight: 700; letter-spacing: 1.4px;"
    )
    apply_secondary_text(topic_eyebrow)
    topic_layout.addWidget(topic_eyebrow)
    topic_title = QLabel(previous_topic.topic_label or "No parsed topic")
    topic_title.setStyleSheet("font-size: 26px; font-weight: 650;")
    topic_title.setWordWrap(True)
    topic_layout.addWidget(topic_title)
    path = "  →  ".join(previous_topic.topic_path) or "No hierarchy available"
    topic_path = QLabel(path)
    topic_path.setWordWrap(True)
    topic_layout.addWidget(topic_path)
    details = QLabel(
        f"Deck: {previous_topic.deck_name or 'Unknown'}\n"
        f"State then: {previous_topic.state.title()}\n"
        f"Reviews: {previous_topic.reps} · Lapses: {previous_topic.lapses}\n"
        f"Seen: {_shown_time(previous_topic.shown_at)}"
    )
    details.setStyleSheet("margin-top: 18px;")
    apply_secondary_text(details)
    details.setWordWrap(True)
    topic_layout.addWidget(details)
    if previous_topic.source_badges:
        source = QLabel("Sources: " + " · ".join(previous_topic.source_badges))
        source.setStyleSheet("margin-top: 12px;")
        source.setWordWrap(True)
        topic_layout.addWidget(source)
    topic_layout.addStretch(1)
    tabs.addTab(topic_page, "Previous topic")

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
    web.cleanup()
