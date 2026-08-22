from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UIContrastTests(unittest.TestCase):
    def test_native_ui_does_not_use_fixed_grey_secondary_text(self) -> None:
        offenders: list[str] = []
        for path in (ROOT / "ui").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in ("color: #777", "color:#777", "color: #666", "palette(mid)"):
                if token in source:
                    offenders.append(f"{path.name}: {token}")
        self.assertEqual(offenders, [])

    def test_shared_theme_blends_native_foreground_and_background(self) -> None:
        source = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
        self.assertIn("QPalette.ColorRole.WindowText", source)
        self.assertIn("QPalette.ColorRole.Window", source)

    def test_literal_ampersands_are_escaped_in_qt_actions_and_buttons(self) -> None:
        settings = (ROOT / "ui" / "settings.py").read_text(encoding="utf-8")
        menu = (ROOT / "ui" / "menu.py").read_text(encoding="utf-8")
        self.assertNotIn('QPushButton("Open Commands & Help")', settings)
        self.assertNotIn('QAction("Commands & Help…"', menu)
        self.assertIn("Open Commands && Help", settings)
        self.assertIn("Commands && Help…", menu)


if __name__ == "__main__":
    unittest.main()
