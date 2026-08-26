"""Native learner-facing Session Debrief and combined history surfaces."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Callable

from ..sessions.debrief import SessionDebrief
from ..sessions.generated_decks import GeneratedDeckHistory
from ..sessions.models import Session
from .history import history_details_html
from .theme import secondary_css


def _duration(milliseconds: int | None, elapsed_seconds: int) -> tuple[str, str]:
    if milliseconds is not None:
        seconds = max(0, round(milliseconds / 1000))
        kind = "active review time"
    else:
        seconds = max(0, elapsed_seconds)
        kind = "elapsed time"
    minutes, remainder = divmod(seconds, 60)
    if minutes:
        return (f"{minutes}m {remainder:02d}s" if remainder else f"{minutes}m", kind)
    return (f"{seconds}s", kind)


def _when(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M")


def debrief_html(debrief: SessionDebrief, *, muted_color: str = "#707070") -> str:
    duration, duration_kind = _duration(
        debrief.active_duration_ms, debrief.elapsed_seconds
    )
    repeated = (
        '<td class="summary-cell"><strong>'
        f"{debrief.answer_count}</strong><br><small>total answers</small></td>"
        if debrief.answer_count != debrief.unique_card_count
        else ""
    )
    pace = ""
    if debrief.pace_delta_percent is not None:
        delta = debrief.pace_delta_percent
        direction = "slower" if delta > 0 else "faster"
        pace = (
            '<div class="vellum-callout"><b>Pace</b><br>'
            f"Your recorded answer pace was about {abs(round(delta))}% {direction} "
            "than Vellum’s starting estimate.</div>"
        )
    topics = ""
    if debrief.topics:
        rows = []
        for topic in debrief.topics:
            marker = '<br><span class="vellum-cluster">Error cluster</span>' if topic.error_cluster else ""
            path = " › ".join(topic.path) if topic.path else topic.label
            rows.append(
                "<tr>"
                f"<td><b>{escape(topic.label)}</b><br><small>{escape(path)}</small>{marker}</td>"
                f"<td>{topic.unique_cards}</td><td>{topic.answer_count}</td>"
                f"<td>{topic.again_count}</td><td>{topic.hard_count}</td>"
                "</tr>"
            )
        topics = (
            "<h2>Topics encountered</h2><table><thead><tr><th>Topic</th>"
            "<th>Cards</th><th>Answers</th><th>Again</th><th>Hard</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    notes = ""
    if debrief.mind_notes:
        groups = []
        for event_type, heading in (
            ("created", "Created during this session"),
            ("resurfaced", "Resurfaced during this session"),
        ):
            note_rows = [
                '<div class="vellum-note">'
                f"<small>{escape(note.topic_label)}</small>"
                f"<p>{escape(note.body)}</p></div>"
                for note in debrief.mind_notes
                if note.event_type == event_type
            ]
            if note_rows:
                groups.append(f"<h3>{heading}</h3>{''.join(note_rows)}")
        notes = f"<h2>Mind Notes</h2>{''.join(groups)}"
    clusters = [topic for topic in debrief.topics if topic.error_cluster]
    cluster_summary = ""
    if clusters:
        cluster_summary = (
            "<h2>Where errors clustered</h2><div class='vellum-callout'>"
            + "<br>".join(
                f"<b>{escape(topic.label)}</b> · {topic.again_count} Again, "
                f"{topic.hard_count} Hard"
                for topic in clusters
            )
            + "</div>"
        )
    remaining = ""
    if debrief.status == "abandoned" and debrief.remaining_card_count:
        remaining = (
            '<div class="vellum-callout">'
            f"<b>{debrief.remaining_card_count} unanswered cards</b><br>"
            "They were returned safely to Anki. This finished session is not presented as resumable."
            "</div>"
        )
    suggestion = debrief.suggestion
    return f"""
    <style>
      body {{ font-family: system-ui, "Segoe UI", sans-serif; line-height:1.45;
              color: palette(text); margin: 4px 10px 24px; }}
      h1 {{ font-size:25px; margin:0 0 4px; }} h2 {{ font-size:17px; margin-top:24px; }}
      .subtle, small {{ color: {escape(muted_color)}; }}
      .summary {{ width:100%; margin:16px 0 10px; border-collapse:collapse; }}
      .summary td {{ border:0; padding:8px 18px 8px 0; vertical-align:top; }}
      .summary strong {{ font-size:24px; }}
      .ratings {{ width:100%; margin:6px 0 18px; border-collapse:separate; }}
      .ratings td {{ border:1px solid rgba(127,127,127,.28); padding:8px 12px;
                     vertical-align:top; }}
      .vellum-callout {{ border-left:3px solid palette(highlight); padding:10px 13px;
                         margin:14px 0; background:rgba(127,127,127,.08); }}
      table {{ border-collapse:collapse; width:100%; }}
      th,td {{ border-bottom:1px solid rgba(127,127,127,.24); padding:8px; text-align:left; }}
      .vellum-cluster {{ display:inline-block; margin:5px 0 0 8px; padding:2px 6px;
                         border-radius:10px; background:rgba(190,110,60,.18); font-size:10px; }}
      .vellum-note {{ border:1px solid rgba(127,127,127,.24); border-radius:10px;
                      padding:10px 12px; margin:8px 0; }} .vellum-note p {{ margin:4px 0 0; }}
    </style>
    <h1>{debrief.unique_card_count} {'card' if debrief.unique_card_count == 1 else 'cards'} reviewed</h1>
    <div class="subtle">{escape(_when(debrief.ended_at))}</div>
    <table class="summary"><tr>
      <td><strong>{debrief.unique_card_count}</strong><br><small>unique cards</small></td>
      <td><strong>{escape(duration)}</strong><br><small>{escape(duration_kind)}</small></td>
      {repeated}
    </tr></table>
    <table class="ratings"><tr>
      <td><b>{debrief.again_count}</b><br><small>Again</small></td>
      <td><b>{debrief.hard_count}</b><br><small>Hard</small></td>
      <td><b>{debrief.good_count}</b><br><small>Good</small></td>
      <td><b>{debrief.easy_count}</b><br><small>Easy</small></td>
    </tr></table>
    {pace}{remaining}
    <div class="vellum-callout"><b>{escape(str(suggestion.get('title') or 'Done for now'))}</b><br>
      {escape(str(suggestion.get('detail') or 'No extra action is required.'))}</div>
    {cluster_summary}{topics}{notes}
    """


def show_debrief(
    parent: Any,
    debrief: SessionDebrief,
    *,
    history: GeneratedDeckHistory | None,
    handoff_enabled: bool,
    on_save_handoff: Callable[[str], None],
    on_suggestion: Callable[[], None] | None,
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        Qt,
        QTextBrowser,
        QToolButton,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Session Debrief")
    dialog.setMinimumSize(760, 650)
    layout = QVBoxLayout(dialog)
    browser = QTextBrowser()
    browser.setOpenExternalLinks(False)
    browser.setHtml(debrief_html(debrief, muted_color=secondary_css(browser)))
    layout.addWidget(browser, 1)

    if on_suggestion is not None and debrief.suggestion.get("kind") != "done":
        action = QPushButton(str(debrief.suggestion.get("title") or "Open"))
        qconnect(action.clicked, lambda: (dialog.accept(), on_suggestion()))
        layout.addWidget(action)

    if handoff_enabled:
        handoff_label = QLabel("Handoff to your future self")
        handoff_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(handoff_label)
        handoff_row = QHBoxLayout()
        handoff = QLineEdit(debrief.handoff_text or "")
        handoff.setMaxLength(280)
        handoff.setPlaceholderText("Next time, I want to…")
        save = QPushButton("Save Handoff")
        qconnect(save.clicked, lambda: on_save_handoff(handoff.text()))
        handoff_row.addWidget(handoff, 1)
        handoff_row.addWidget(save)
        layout.addLayout(handoff_row)

    if history is not None:
        details_toggle = QToolButton()
        details_toggle.setText("Technical session details")
        details_toggle.setCheckable(True)
        details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        details = QTextBrowser()
        details.setHtml(
            history_details_html(history, muted_color=secondary_css(details))
        )
        details.setMinimumHeight(300)
        details.setVisible(False)

        def toggle(checked: bool) -> None:
            details.setVisible(checked)
            details_toggle.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )

        qconnect(details_toggle.toggled, toggle)
        layout.addWidget(details_toggle)
        layout.addWidget(details)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()


def show_debrief_history(
    parent: Any,
    debriefs: tuple[SessionDebrief, ...],
    legacy_histories: tuple[GeneratedDeckHistory, ...],
    legacy_sessions: tuple[Session, ...],
    *,
    open_debrief: Callable[[str], None],
) -> None:
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

    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Session History")
    dialog.setMinimumSize(900, 620)
    layout = QVBoxLayout(dialog)
    title = QLabel("Session history")
    title.setStyleSheet("font-size: 22px; font-weight: 650;")
    layout.addWidget(title)
    sessions = QListWidget()
    layout.addWidget(sessions, 1)
    ordered: list[tuple[str, str]] = []
    for item in debriefs:
        source = {
            "time_machine": "Study by Time",
            "recovery": "Recovery",
            "normal": "Regular study",
        }.get(item.origin, "Study session")
        sessions.addItem(
            f"{source} · {_when(item.ended_at)}\n"
            f"{item.unique_card_count} cards · {item.status.title()}"
        )
        ordered.append(("debrief", item.session_id))
    debrief_ids = {item.session_id for item in debriefs}
    generated_ids = {history.session_id for history in legacy_histories}
    for session in legacy_sessions:
        if session.id in debrief_ids or session.id in generated_ids:
            continue
        source = "Regular study" if session.origin.value == "normal" else "Study session"
        ended_at = int(session.ended_at or session.last_active_at)
        sessions.addItem(
            f"{source} · {_when(ended_at)}\n"
            "Learning summary unavailable for this older session · Technical history retained"
        )
        ordered.append(("legacy", session.id))
    for history in legacy_histories:
        if history.session_id in debrief_ids:
            continue
        sessions.addItem(
            f"Older {history.feature.replace('_', ' ').title()} session · {_when(history.created_at)}\n"
            "Learning summary unavailable for this older session · Technical history retained"
        )
        ordered.append(("legacy", history.session_id))
    if not ordered:
        empty = QTextBrowser()
        empty.setHtml("<h2>No sessions yet</h2><p>Completed study sessions will appear here.</p>")
        layout.addWidget(empty)

    def activated(row: int) -> None:
        if 0 <= row < len(ordered) and ordered[row][0] == "debrief":
            dialog.accept()
            open_debrief(ordered[row][1])

    qconnect(sessions.itemActivated, lambda _item: activated(sessions.currentRow()))
    controls = QHBoxLayout()
    open_button = QPushButton("Open Debrief")
    qconnect(open_button.clicked, lambda: activated(sessions.currentRow()))
    qconnect(
        sessions.currentRowChanged,
        lambda row: open_button.setEnabled(
            0 <= row < len(ordered) and ordered[row][0] == "debrief"
        ),
    )
    sessions.setCurrentRow(0 if ordered else -1)
    controls.addWidget(open_button)
    controls.addStretch(1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    controls.addWidget(buttons)
    layout.addLayout(controls)
    dialog.exec()
