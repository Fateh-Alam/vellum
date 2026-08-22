"""Keyboard-first Recovery selection, preview, and native deck handoff."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Callable

from ..core.config import RecoveryConfig
from ..recovery.models import RecoveryCustomOptions, RecoveryMode, RecoveryPlan


@dataclass(frozen=True)
class RecoverySelection:
    level_index: int
    mode: RecoveryMode
    custom: RecoveryCustomOptions


def unique_deck_name(collection: Any, requested: str) -> str:
    """Return a readable Recovery name that cannot reuse an existing deck."""

    candidate = requested.strip() or "Vellum Recovery"
    if collection.decks.id_for_name(candidate) is None:
        return candidate
    suffix = 2
    while collection.decks.id_for_name(f"{candidate} ({suffix})") is not None:
        suffix += 1
    return f"{candidate} ({suffix})"


def show_recovery_dialog(
    parent: Any,
    path: tuple[str, ...],
    *,
    default_level_index: int,
    config: RecoveryConfig,
) -> RecoverySelection | None:
    from aqt.qt import (  # type: ignore[import-not-found]
        QButtonGroup,
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QGroupBox,
        QKeySequence,
        QLabel,
        QRadioButton,
        QSpinBox,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Recover Topic")
    dialog.setMinimumWidth(440)
    layout = QVBoxLayout(dialog)

    title = QLabel("Repair the knowledge gap exposed by this card")
    title.setStyleSheet("font-size: 16px; font-weight: 600;")
    layout.addWidget(title)
    intro = QLabel("Choose how broadly Vellum should recover, then choose its depth.")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    level_box = QGroupBox("Recovery level")
    level_layout = QVBoxLayout(level_box)
    level_group = QButtonGroup(dialog)
    level_buttons: dict[int, Any] = {}
    for level_index in reversed(range(len(path))):
        button = QRadioButton(path[level_index])
        button.setChecked(level_index == default_level_index)
        level_group.addButton(button, level_index)
        level_buttons[level_index] = button
        level_layout.addWidget(button)
    layout.addWidget(level_box)

    mode_box = QGroupBox("Recovery mode")
    mode_layout = QVBoxLayout(mode_box)
    mode_group = QButtonGroup(dialog)
    descriptions = {
        RecoveryMode.QUICK: "&1  Quick — weakest cards, minimal intervention",
        RecoveryMode.STANDARD: "&2  Standard — weak cards plus suggested starting cards",
        RecoveryMode.FULL: "&3  Full — broader topic repair",
        RecoveryMode.CUSTOM: "&4  Custom — choose the inclusion rules",
    }
    mode_buttons: dict[RecoveryMode, Any] = {}
    for mode, label in descriptions.items():
        button = QRadioButton(label)
        button.setShortcut(QKeySequence(str(len(mode_buttons) + 1)))
        button.setChecked(mode.value == config.default_mode)
        mode_group.addButton(button)
        mode_buttons[mode] = button
        mode_layout.addWidget(button)
    layout.addWidget(mode_box)

    custom_box = QGroupBox("Custom options")
    custom_layout = QVBoxLayout(custom_box)
    count = QSpinBox()
    count.setRange(1, 500)
    count.setValue(min(config.max_standard, 500))
    count.setPrefix("Card count: ")
    custom_layout.addWidget(count)
    include_new = QCheckBox("Include new cards")
    include_new.setChecked(config.include_new)
    include_mature = QCheckBox("Include mature cards")
    include_mature.setChecked(True)
    include_failed = QCheckBox("Include recently failed cards")
    include_failed.setChecked(True)
    include_current = QCheckBox("Include current card")
    include_current.setChecked(config.include_current)
    difficult = QCheckBox("Prioritize difficult cards")
    difficult.setChecked(True)
    for widget in (
        include_new,
        include_mature,
        include_failed,
        include_current,
        difficult,
    ):
        custom_layout.addWidget(widget)
    custom_box.setVisible(mode_buttons[RecoveryMode.CUSTOM].isChecked())
    layout.addWidget(custom_box)

    for button in mode_buttons.values():
        qconnect(
            button.toggled,
            lambda _checked, box=custom_box: box.setVisible(
                mode_buttons[RecoveryMode.CUSTOM].isChecked()
            ),
        )

    note = QLabel(
        "Up/Down changes a selected hierarchy or mode. Keys 1-4 select a mode."
    )
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok
        | QDialogButtonBox.StandardButton.Cancel
    )
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if ok is not None:
        ok.setText("Preview Recovery")
        ok.setDefault(True)
    layout.addWidget(buttons)
    qconnect(buttons.accepted, dialog.accept)
    qconnect(buttons.rejected, dialog.reject)
    level_buttons[default_level_index].setFocus()
    if not dialog.exec():
        return None

    level_index = next(
        index for index, button in level_buttons.items() if button.isChecked()
    )
    mode = next(mode for mode, button in mode_buttons.items() if button.isChecked())
    return RecoverySelection(
        level_index=level_index,
        mode=mode,
        custom=RecoveryCustomOptions(
            card_count=count.value(),
            include_new=include_new.isChecked(),
            include_mature=include_mature.isChecked(),
            include_recently_failed=include_failed.isChecked(),
            include_current=include_current.isChecked(),
            prioritize_difficult=difficult.isChecked(),
        ),
    )


def confirm_recovery_plan(
    parent: Any,
    plan: RecoveryPlan,
    *,
    excluded_count: int,
) -> bool:
    from aqt.qt import (  # type: ignore[import-not-found]
        QDialog,
        QDialogButtonBox,
        QLabel,
        QTextBrowser,
        QVBoxLayout,
        qconnect,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Recovery Preview")
    dialog.setMinimumSize(500, 430)
    layout = QVBoxLayout(dialog)
    title = QLabel(f"{escape(plan.topic_label)} · {len(plan.cards)} cards")
    title.setStyleSheet("font-size: 17px; font-weight: 600;")
    layout.addWidget(title)
    summary = QLabel(
        f"{plan.mode.value.title()} Recovery selected {len(plan.cards)} of "
        f"{plan.available_count} available cards."
    )
    summary.setWordWrap(True)
    layout.addWidget(summary)

    lines: list[str] = []
    for index, card in enumerate(plan.cards[:12], start=1):
        labels: list[str] = []
        if card.suggested_starting:
            labels.append("Suggested starting card")
        if card.candidate.is_current:
            labels.append("Current card")
        reason = "; ".join(card.reasons[:3]) or "related topic card"
        suffix = f" — {', '.join(labels)}" if labels else ""
        lines.append(
            f"<p><b>{index}. Card {card.candidate.card_id}</b> · "
            f"score {card.score:g}{escape(suffix)}<br>{escape(reason)}</p>"
        )
    if len(plan.cards) > 12:
        lines.append(f"<p>…and {len(plan.cards) - 12} more selected cards.</p>")
    details = QTextBrowser()
    details.setHtml("".join(lines))
    layout.addWidget(details, 1)

    safety = QLabel(
        "Anki's native filtered-deck window opens next. Cards remain linked to "
        "their home decks. Keep Reschedule enabled for normal scheduling; changing "
        "it creates a preview-style cram session instead."
    )
    if excluded_count:
        safety.setText(
            safety.text()
            + f" {excluded_count} suspended, buried, or already-filtered card(s) "
            "were excluded because Anki cannot safely pull them."
        )
    safety.setWordWrap(True)
    layout.addWidget(safety)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok
        | QDialogButtonBox.StandardButton.Cancel
    )
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if ok is not None:
        ok.setText("Continue to Anki Filtered Deck…")
    layout.addWidget(buttons)
    qconnect(buttons.accepted, dialog.accept)
    qconnect(buttons.rejected, dialog.reject)
    return bool(dialog.exec())


def open_native_filtered_deck(
    mw: Any,
    *,
    plan: RecoveryPlan,
    deck_name: str,
    on_created: Callable[[int, str], None],
) -> Any:
    """Use Anki's own filtered-deck UI so cancel/reschedule remain native."""

    from aqt.filtered_deck import (  # type: ignore[import-not-found]
        FilteredDeckConfigDialog,
    )
    from aqt import gui_hooks  # type: ignore[import-not-found]
    from aqt.utils import showWarning  # type: ignore[import-not-found]

    query = "cid:" + ",".join(str(card_id) for card_id in plan.card_ids)
    deck_name = unique_deck_name(mw.col, deck_name)

    class VellumFilteredDeckDialog(FilteredDeckConfigDialog):
        _vellum_created_hook: Any | None = None

        def _load_deck(self) -> None:
            super()._load_deck()
            self.form.name.setText(deck_name)
            self.form.search.setText(query)
            self.form.limit.setValue(len(plan.cards))
            self.form.resched.setChecked(True)

        def _update_deck(self) -> bool:
            if not super()._update_deck():
                return False
            existing_id = self.col.decks.id_for_name(self.deck.name)
            if existing_id is not None and int(existing_id) != int(self.deck.id):
                showWarning(
                    "That deck name already exists. Choose a unique Recovery deck name.",
                    parent=self,
                )
                self.form.name.setFocus()
                self.form.name.selectAll()
                return False
            return True

        def reject(self) -> None:
            self._remove_vellum_hook()
            super().reject()

        def _remove_vellum_hook(self) -> None:
            callback = self._vellum_created_hook
            if callback is None:
                return
            try:
                gui_hooks.filtered_deck_dialog_did_add_or_update_deck.remove(
                    callback
                )
            except ValueError:
                pass
            self._vellum_created_hook = None

    dialog = VellumFilteredDeckDialog(mw, search=query)

    def created(source: Any, deck: Any, deck_id: int) -> None:
        if source is not dialog:
            return
        dialog._remove_vellum_hook()
        on_created(int(deck_id), str(deck.name))

    gui_hooks.filtered_deck_dialog_did_add_or_update_deck.append(created)
    dialog._vellum_created_hook = created
    return dialog
