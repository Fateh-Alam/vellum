import unittest
from pathlib import Path

from vellum.core.config import VellumConfig
from vellum.ui.onboarding import (
    ONBOARDING_VERSION,
    detect_likely_roots,
    should_auto_open,
    should_offer_invitation,
)


class OnboardingTests(unittest.TestCase):
    def test_fresh_install_opens_v2_setup(self) -> None:
        config = VellumConfig()
        self.assertTrue(should_auto_open(config))
        self.assertFalse(should_offer_invitation(config))

    def test_existing_completed_user_receives_one_invitation(self) -> None:
        upgraded = VellumConfig.from_mapping(
            {"config_version": 1, "onboarding_completed": True}
        )
        self.assertFalse(should_auto_open(upgraded))
        self.assertTrue(should_offer_invitation(upgraded))
        dismissed = VellumConfig.from_mapping(
            {
                **upgraded.to_mapping(),
                "onboarding_invitation_version": ONBOARDING_VERSION,
            }
        )
        self.assertFalse(should_offer_invitation(dismissed))

    def test_detects_preferred_roots_without_card_text(self) -> None:
        roots = detect_likely_roots(
            (
                "#AK_Step1_v12::#FirstAid::Renal::Pathology",
                "#AK_Step1_v12::#SketchyMicro::Bacteria",
            ),
            ("#FirstAid", "#SketchyMicro"),
        )
        self.assertEqual(roots, ("#FirstAid", "#SketchyMicro"))

    def test_onboarding_never_uses_unreadable_mid_palette_text(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "ui" / "onboarding.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("palette(mid)", source)

    def test_ready_actions_do_not_expose_qt_mnemonic_artifacts(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "ui" / "onboarding.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('QPushButton("Finish &', source)
        self.assertIn('QPushButton("Finish, then Start Time Machine")', source)


if __name__ == "__main__":
    unittest.main()
