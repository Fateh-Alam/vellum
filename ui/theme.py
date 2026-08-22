"""Small palette helpers shared by Vellum's native Qt surfaces.

The helpers are deliberately lazy so importing Vellum's pure modules never
requires Anki or Qt.  Secondary text is blended from the active native
foreground/background instead of using a fixed grey, which keeps it readable
in light, dark, high-contrast, and custom Anki themes.
"""

from __future__ import annotations

from typing import Any


def secondary_color(widget: Any, *, strength: float = 0.68) -> Any:
    """Return an opaque, theme-aware secondary-text QColor."""

    from aqt.qt import QColor, QPalette  # type: ignore[import-not-found]

    ratio = min(1.0, max(0.0, float(strength)))
    palette = widget.palette()
    foreground = palette.color(QPalette.ColorRole.WindowText)
    background = palette.color(QPalette.ColorRole.Window)
    return QColor(
        round(background.red() + (foreground.red() - background.red()) * ratio),
        round(background.green() + (foreground.green() - background.green()) * ratio),
        round(background.blue() + (foreground.blue() - background.blue()) * ratio),
    )


def apply_secondary_text(widget: Any, *, strength: float = 0.68) -> None:
    """Apply readable secondary text without replacing other palette roles."""

    from aqt.qt import QPalette  # type: ignore[import-not-found]

    palette = widget.palette()
    palette.setColor(
        QPalette.ColorRole.WindowText,
        secondary_color(widget, strength=strength),
    )
    widget.setPalette(palette)


def secondary_css(widget: Any, *, strength: float = 0.68) -> str:
    """Return a CSS hex color derived from the widget's active native palette."""

    return secondary_color(widget, strength=strength).name()
