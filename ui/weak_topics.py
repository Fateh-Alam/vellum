"""Recent-topic health overview; intentionally avoids whole-collection scans."""

from __future__ import annotations

from typing import Any

from ..anki.topic_stats import collect_topic_stats
from ..topics.health import describe_topic_health


def show_weak_topics(mw: Any, app: Any) -> None:
    from aqt.operations import QueryOp  # type: ignore[import-not-found]
    from aqt.utils import showInfo  # type: ignore[import-not-found]

    if not app.config.modules.topic_health:
        showInfo("Enable Topic Health in Vellum Settings first.", parent=mw)
        return
    recent = app.services.topics.recent_topics(20)
    if not recent:
        showInfo(
            "No recent topic context is available yet. Review a few tagged cards first.",
            parent=mw,
        )
        return

    def collect(collection: Any) -> list[tuple[str, str, int, int, str]]:
        rows: list[tuple[str, str, int, int, str]] = []
        for parsed in recent:
            if not parsed.raw_tag or not parsed.path:
                continue
            stats = collect_topic_stats(collection, parsed.raw_tag)
            rows.append(
                (
                    parsed.path[-1],
                    stats.health_state or "Insufficient Data",
                    stats.recent_failures,
                    stats.due_cards,
                    describe_topic_health(stats),
                )
            )
        priority = {
            "Needs Recovery": 0,
            "Fading": 1,
            "Stable": 2,
            "Strong": 3,
            "Insufficient Data": 4,
        }
        rows.sort(key=lambda row: (priority.get(row[1], 5), row[0].casefold()))
        return rows

    QueryOp(parent=mw, op=collect, success=lambda rows: _show(mw, rows)).run_in_background()


def _show(parent: Any, rows: list[tuple[str, str, int, int, str]]) -> None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QAbstractItemView,
        QLabel,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Vellum Topic Health")
    dialog.resize(620, 440)
    layout = QVBoxLayout(dialog)
    title = QLabel("Recently encountered topics")
    title.setStyleSheet("font-size: 18px; font-weight: 650;")
    layout.addWidget(title)
    note = QLabel(
        "Topic Health is a workflow heuristic from recent reviews and due cards, "
        "not a scientific memory or mastery score."
    )
    note.setWordWrap(True)
    layout.addWidget(note)
    table = QTableWidget(len(rows), 5)
    table.setHorizontalHeaderLabels(
        ("Topic", "State", "Recent Again cards", "Due", "Why")
    )
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            table.setItem(row_index, column, QTableWidgetItem(str(value)))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(table, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    qconnect(buttons.rejected, dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
