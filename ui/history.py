"""Native, local-only browser for Vellum-generated deck history."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from typing import Any

from ..sessions.generated_decks import GeneratedDeckHistory
from .theme import secondary_css


RATING_LABELS = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}


def _when(timestamp: int | None) -> str:
    if timestamp is None:
        return "—"
    return datetime.fromtimestamp(timestamp).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )


def history_details_html(
    history: GeneratedDeckHistory, *, muted_color: str = "#707070"
) -> str:
    """Render one complete, privacy-safe deck manifest and answer timeline."""

    answers_by_card: dict[int, list[Any]] = defaultdict(list)
    for answer in history.answers:
        answers_by_card[answer.card_id].append(answer)

    rows: list[str] = []
    for card in history.cards:
        answers = answers_by_card.get(card.card_id, [])
        answer_lines = []
        for answer in answers:
            duration = (
                f" · {answer.duration_ms / 1000:.1f}s"
                if answer.duration_ms is not None
                else ""
            )
            answer_lines.append(
                f"{escape(_when(answer.answered_at // 1000))} · "
                f"{escape(RATING_LABELS.get(answer.rating, str(answer.rating)))}"
                f"{duration}"
            )
        answer_html = "<br>".join(answer_lines) if answer_lines else "Not answered"
        home = card.original_deck_name or (
            str(card.original_deck_id) if card.original_deck_id is not None else "—"
        )
        rows.append(
            "<tr>"
            f"<td>{card.queue_position}</td>"
            f"<td><code>{card.card_id}</code></td>"
            f"<td><code>{card.note_id or '—'}</code></td>"
            f"<td>{escape(home)}</td>"
            f"<td>{escape(card.bucket or '—')}</td>"
            f"<td>{answer_html}</td>"
            "</tr>"
        )

    feature = "Study by Time" if history.feature == "time_machine" else "Recovery"
    removed = (
        f"{_when(history.removed_at)} ({history.removal_reason})"
        if history.removed_at is not None
        else "Not removed"
    )
    metadata = "".join(
        f"<dt>{escape(str(key).replace('_', ' ').title())}</dt>"
        f"<dd>{escape(str(value))}</dd>"
        for key, value in sorted(history.metadata.items())
    )
    return f"""
    <style>
      body {{ font-family: system-ui, "Segoe UI", sans-serif; line-height: 1.4; }}
      h1 {{ font-size: 22px; margin: 0 0 4px; }}
      .subtle {{ color: {escape(muted_color)}; margin: 0 0 18px; }}
      .metrics {{ width: 100%; margin: 14px 0 18px; }}
      .metrics td {{ width: 25%; border: 0; padding: 10px 14px 10px 0; }}
      .metrics strong {{ font-size: 20px; }}
      .details {{ width: 100%; margin: 4px 0 20px; }}
      .details td {{ border: 0; padding: 3px 10px 3px 0; }}
      .details td:first-child {{ color: {escape(muted_color)}; width: 155px; }}
      table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
      th, td {{ border-bottom: 1px solid rgba(127,127,127,.25); padding: 8px;
                text-align: left; vertical-align: top; }}
      th {{ position: sticky; top: 0; background: palette(base); }}
      code {{ font-family: ui-monospace, monospace; }}
    </style>
    <h1>{escape(feature)} · {escape(history.deck_name)}</h1>
    <p class="subtle">Session <code>{escape(history.session_id)}</code></p>
    <table class="metrics"><tr>
      <td><strong>{history.planned_card_count}</strong><br>Cards planned</td>
      <td><strong>{len(history.cards)}</strong><br>Card records retained</td>
      <td><strong>{history.answered_card_count}</strong><br>Unique cards answered</td>
      <td><strong>{len(history.answers)}</strong><br>Total answers</td>
    </tr></table>
    <table class="details">
      <tr><td>Status</td><td>{escape(history.status.title())}</td></tr>
      <tr><td>Created</td><td>{escape(_when(history.created_at))}</td></tr>
      <tr><td>Ended</td><td>{escape(_when(history.ended_at))}</td></tr>
      <tr><td>Filtered deck removed</td><td>{escape(removed)}</td></tr>
      <tr><td>Scope</td><td>{escape(history.scope or '—')}</td></tr>
      <tr><td>Target</td><td>{history.target_seconds or '—'} seconds</td></tr>
      {metadata.replace('<dt>', '<tr><td>').replace('</dt><dd>', '</td><td>').replace('</dd>', '</td></tr>')}
    </table>
    {('<p><b>Legacy reconstruction:</b> this session predates full manifest tracking. '
      'Vellum retained every recoverable card record, but the original complete '
      'deck membership is unavailable.</p>'
      if history.metadata.get('manifest_complete') is False else '')}
    <h2>{'Complete' if history.metadata.get('manifest_complete', True) else 'Reconstructed'} card manifest</h2>
    <table>
      <thead><tr><th>#</th><th>Card ID</th><th>Note ID</th><th>Home deck</th>
      <th>State</th><th>Answer history</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


def show_generated_deck_history(parent: Any, repository: Any) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QLabel,
        QListWidget,
        QSplitter,
        QTextBrowser,
        QVBoxLayout,
        Qt,
        qconnect,
    )

    histories = repository.recent_summaries(limit=200)
    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Session History")
    dialog.setMinimumSize(1050, 650)
    layout = QVBoxLayout(dialog)
    title = QLabel("Generated deck history")
    title.setStyleSheet("font-size: 20px; font-weight: 650;")
    layout.addWidget(title)
    intro = QLabel(
        "Every Study by Time and Recovery deck is recorded from creation onward. "
        "Its complete manifest remains after the temporary deck is removed; "
        "card text is never copied."
    )
    intro.setWordWrap(True)
    layout.addWidget(intro)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    sessions = QListWidget()
    sessions.setMinimumWidth(280)
    details = QTextBrowser()
    details.setOpenExternalLinks(False)
    splitter.addWidget(sessions)
    splitter.addWidget(details)
    splitter.setStretchFactor(1, 1)
    layout.addWidget(splitter, 1)

    if not histories:
        details.setHtml(
            "<h2>No generated decks yet</h2>"
            "<p>Your completed Study by Time and Recovery sessions will appear here.</p>"
        )
    else:
        for history in histories:
            feature = "Study by Time" if history.feature == "time_machine" else "Recovery"
            sessions.addItem(
                f"{feature} · {_when(history.created_at)}\n"
                f"{history.planned_card_count} cards · {history.status.title()}"
            )

        def selected(row: int) -> None:
            if 0 <= row < len(histories):
                history = repository.get(histories[row].history_id)
                if history is not None:
                    details.setHtml(
                        history_details_html(
                            history, muted_color=secondary_css(details)
                        )
                    )

        qconnect(sessions.currentRowChanged, selected)
        sessions.setCurrentRow(0)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
