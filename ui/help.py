"""Always-available, fully offline Vellum instructions and command legend."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any

from ..anki.commands import command_views
from .theme import secondary_css

if TYPE_CHECKING:
    from ..bootstrap import VellumApplication


PRODUCT_PROMISE = (
    "Vellum is a local-first continuity layer. Anki and FSRS remain fully "
    "responsible for scheduling; Vellum adds context, time-boxing, recovery, "
    "and safe return to unfinished work."
)
PRIVACY_PROMISE = (
    "No account · No telemetry · No cloud backend · Card text is never copied"
)


HELP_SECTIONS = (
    (
        "Start Here",
        """
        <h1>Start Here</h1>
        <p><b>Anki remembers your cards. Vellum remembers your studying.</b></p>
        <p>Vellum adds context, interruption-safe sessions, realistic time-boxing,
        and deliberate topic repair without replacing Anki or FSRS.</p>
        <h2>A simple first session</h2>
        <ol><li>Open any deck and begin reviewing.</li>
        <li>Use Context when you need the larger topic hierarchy.</li>
        <li>Use Recovery when one failed card reveals a broader gap.</li>
        <li>Use Time Machine when your available time is the real constraint.</li></ol>
        """,
    ),
    (
        "Core Workflows",
        """
        <h1>Core Workflows</h1>
        <h2>Context</h2><p>A compact, optional topic layer inside Reviewer.</p>
        <h2>Recovery</h2><p>Select a hierarchy level and create a transparent,
        temporary filtered deck. Anki remains responsible for scheduling.</p>
        <h2>Time Machine</h2><p>Choose a duration and deck scope. Vellum estimates a
        bounded queue from your local pace and safe fallbacks.</p>
        <h2>Resume and Return Ramp</h2><p>Resume explains whether the old queue still
        matches. Return Ramp offers a calm re-entry after an absence.</p>
        <h2>Debrief</h2><p>Generated sessions finish with a quiet Deck Browser card.
        Open it for rating patterns, topic clusters, notes, and an optional handoff.</p>
        """,
    ),
    (
        "Commands & Conflicts",
        """
        <h1>Commands and Conflict Resolution</h1><p>Vellum stores portable Qt
        key sequences, then asks Qt to display the native label for this operating
        system. Reviewer commands are checked when Reviewer becomes active.</p>
        <p>If a key is already owned by Anki or another add-on, Vellum leaves that
        command inactive. Open Settings to choose a different sequence; Vellum never
        silently overrides the existing action.</p>
        """,
    ),
    (
        "Topic Parsing",
        """
        <h1>Topic Parsing</h1><p>Vellum reads hierarchical tags—not card text—to place
        cards in topics. It supports generic <code>Parent::Child</code> tags and a
        version-tolerant AnKing adapter.</p><p>Use Settings → Topic Parsing to prioritize
        roots, ignore utility hierarchies, rename display segments, and preview the
        current card.</p>
        """,
    ),
    (
        "Sessions & Handoffs",
        """
        <h1>Sessions, Debrief, Resume, and Handoffs</h1><p>Vellum checkpoints answers in its
        private database. Interrupted sessions remain resumable; generated sessions
        become final only after their owned temporary deck is safely handled. Resume
        is for interruption, while an explicitly finished session is terminal and its
        unanswered cards are reported as safely returned to Anki.</p>
        <p>Generated sessions may leave a persistent completion card. Ordinary study
        stays quiet and appears only in Session History. Older sessions without topic
        snapshots retain technical history but do not receive invented summaries.</p>
        <p>A handoff is a single private line for your future self. The newest handoff
        remains on the Deck Browser until you mark it done, replace it, or clear it.</p>
        """,
    ),
    (
        "Privacy",
        """
        <h1>Privacy and Local Data</h1><p>Vellum has no account, telemetry, cloud
        backend, API keys, or external requests. Session records contain identifiers,
        timing, ratings, topic metadata, and text you deliberately enter as a Mind
        Note or handoff. Card question and answer text are never copied.</p>
        <p>Settings → Data can clear individual histories, reset all Vellum data, or
        export redacted diagnostics.</p>
        """,
    ),
    (
        "Troubleshooting",
        """
        <h1>Troubleshooting</h1><ul>
        <li>If a shortcut reports a conflict, change it in Settings rather than
        overriding Anki or another add-on.</li>
        <li>If no topic appears, inspect Topic Parsing and preview the current card.</li>
        <li>If a generated session is unfinished, Resume or Finish it before creating
        another temporary deck.</li>
        <li>If private storage is unavailable, Vellum deliberately degrades to the
        nonpersistent features shown in Settings.</li></ul>
        """,
    ),
)


def _document(body: str, *, muted_color: str = "#707070") -> str:
    return f"""
    <style>
      body {{ font-family: system-ui, "Segoe UI", sans-serif; line-height:1.5;
              color:palette(text); margin:14px 20px 30px; }}
      h1 {{ font-size:24px; }} h2 {{ font-size:17px; margin-top:22px; }}
      code {{ font-family:ui-monospace, "Cascadia Mono", monospace; }}
      table {{ border-collapse:collapse; width:100%; }}
      th,td {{ border-bottom:1px solid rgba(127,127,127,.25); padding:8px;
               text-align:left; vertical-align:top; }}
      .status {{ white-space:nowrap; font-weight:650; }}
      small {{ color:{escape(muted_color)}; }}
    </style>{body}
    """


def commands_html(
    app: "VellumApplication", parent: Any, *, muted_color: str = "#707070"
) -> str:
    rows = []
    for command in command_views(app.config, parent):
        rows.append(
            "<tr>"
            f"<td><b>{escape(command.name)}</b><br><small>{escape(command.purpose)}</small></td>"
            f"<td><code>{escape(command.native_shortcut)}</code></td>"
            f"<td>{escape(command.scope)}</td>"
            f"<td class='status'>{escape(command.status)}<br><small>{escape(command.detail)}</small></td>"
            "</tr>"
        )
    return _document(
        "<h1>Commands</h1><p>Labels below use this computer’s native keyboard notation. "
        "Portable values remain editable in Settings.</p>"
        "<table><thead><tr><th>Command</th><th>Shortcut</th><th>Where</th><th>Status</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>",
        muted_color=muted_color,
    )


def show_help(
    parent: Any,
    app: "VellumApplication",
    *,
    initial_section: str = "Start Here",
) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QListWidget,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Commands & Help")
    dialog.setMinimumSize(900, 650)
    layout = QVBoxLayout(dialog)
    body = QHBoxLayout()
    sections = QListWidget()
    sections.setMaximumWidth(190)
    browser = QTextBrowser()
    browser.setOpenExternalLinks(False)
    muted_color = secondary_css(browser)
    content = [("Commands", commands_html(app, parent, muted_color=muted_color))] + [
        (title, _document(html, muted_color=muted_color)) for title, html in HELP_SECTIONS
    ]
    for title, _html in content:
        sections.addItem(title)
    body.addWidget(sections)
    body.addWidget(browser, 1)
    layout.addLayout(body, 1)

    def selected(row: int) -> None:
        if 0 <= row < len(content):
            browser.setHtml(content[row][1])

    qconnect(sections.currentRowChanged, selected)
    requested = next(
        (index for index, item in enumerate(content) if item[0] == initial_section), 1
    )
    sections.setCurrentRow(requested)
    controls = QHBoxLayout()
    settings = QPushButton("Open Settings")
    qconnect(settings.clicked, lambda: app.services.events.emit("settings_requested"))
    controls.addWidget(settings)
    controls.addStretch(1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    controls.addWidget(buttons)
    layout.addLayout(controls)
    dialog.exec()
