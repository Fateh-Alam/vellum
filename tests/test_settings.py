from __future__ import annotations

from types import SimpleNamespace
import unittest

from vellum.sessions.models import Session, SessionStatus
from vellum.ui.settings import reset_would_break_active_session


class SettingsSafetyTests(unittest.TestCase):
    @staticmethod
    def app_with(status: SessionStatus | None) -> SimpleNamespace:
        session = (
            Session(id="session", started_at=1, last_active_at=1, status=status)
            if status is not None
            else None
        )
        return SimpleNamespace(
            services=SimpleNamespace(sessions=SimpleNamespace(current=session))
        )

    def test_active_session_history_cannot_be_cleared(self) -> None:
        app = self.app_with(SessionStatus.ACTIVE)
        self.assertTrue(reset_would_break_active_session(app, ("sessions",)))
        self.assertTrue(
            reset_would_break_active_session(app, ("generated_deck_history",))
        )

    def test_terminal_or_unrelated_data_can_be_cleared(self) -> None:
        self.assertFalse(
            reset_would_break_active_session(
                self.app_with(SessionStatus.COMPLETED), ("sessions",)
            )
        )
        self.assertFalse(
            reset_would_break_active_session(
                self.app_with(SessionStatus.ACTIVE), ("timing_samples",)
            )
        )
