from dataclasses import replace
import unittest

from vellum.core.config import VellumConfig
from vellum.features.hud import hud_payload
from vellum.sessions.models import Session, SessionOrigin, SessionStatus


class HudTests(unittest.TestCase):
    def test_time_machine_payload_has_live_target_and_estimated_total(self) -> None:
        session = Session(
            id="hud-1",
            started_at=1000,
            last_active_at=1020,
            status=SessionStatus.ACTIVE,
            origin=SessionOrigin.TIME_MACHINE,
            target_seconds=1800,
            reviewed_count=12,
            estimated_total=80,
        )
        payload = hud_payload(session, VellumConfig(), now=1100)
        self.assertEqual(payload["elapsedSeconds"], 100)
        self.assertEqual(payload["remainingSeconds"], 1700)
        self.assertEqual(payload["estimatedTotal"], 80)
        self.assertFalse(payload["showEta"])
        self.assertFalse(payload["showCardsPerMinute"])
        self.assertFalse(payload["showSessionTarget"])

    def test_normal_session_omits_time_target(self) -> None:
        session = Session(
            id="hud-2",
            started_at=1000,
            last_active_at=1000,
            status=SessionStatus.ACTIVE,
            reviewed_count=3,
        )
        payload = hud_payload(session, VellumConfig(), now=1010)
        self.assertIsNone(payload["targetSeconds"])
        self.assertIsNone(payload["remainingSeconds"])


if __name__ == "__main__":
    unittest.main()
