from dataclasses import replace
import unittest

from vellum.core.config import ModuleFlags, VellumConfig


class ConfigTests(unittest.TestCase):
    def test_defaults_match_product_module_policy(self) -> None:
        config = VellumConfig()
        self.assertTrue(config.enabled)
        self.assertTrue(config.modules.context)
        self.assertTrue(config.modules.recovery)
        self.assertTrue(config.modules.return_ramp)
        self.assertTrue(config.modules.backtrack)
        self.assertTrue(config.modules.mind_notes)
        self.assertTrue(config.modules.session_debrief)
        self.assertFalse(config.modules.topic_health)
        self.assertEqual(config.config_version, 3)
        self.assertTrue(config.modules.study_builder)
        self.assertEqual(config.study_builder.default_limit, 100)
        self.assertTrue(config.general.keyboard_shortcuts)
        self.assertEqual(config.topic_parsing.preferred_roots[0], "#FirstAid")
        self.assertEqual(config.context.collapse_shortcut, "Escape")
        self.assertFalse(config.context.auto_collapse_on_new_card)
        self.assertFalse(config.hud.show_cards_per_minute)
        self.assertEqual(config.time_machine.shortcut, "Ctrl+Shift+T")
        self.assertEqual(config.return_ramp.absence_days, 3)
        self.assertEqual(config.backtrack.shortcut, "Alt+B")
        self.assertEqual(config.mind_notes.shortcut, "Alt+M")

    def test_v1_completed_onboarding_upgrades_without_forcing_v2_complete(self) -> None:
        config = VellumConfig.from_mapping(
            {"config_version": 1, "onboarding_completed": True}
        )
        self.assertEqual(config.config_version, 3)
        self.assertTrue(config.onboarding_completed)
        self.assertEqual(config.onboarding_version, 1)
        self.assertEqual(config.onboarding_invitation_version, 0)

    def test_invalid_values_are_safely_normalized(self) -> None:
        config = VellumConfig.from_mapping(
            {
                "enabled": "yes",
                "general": {"theme": "neon", "keyboard_shortcuts": "yes"},
                "context": {
                    "side": "middle",
                    "width": 5000,
                    "collapse_shortcut": "",
                },
                "hud": {"placement": "offscreen"},
                "time_machine": {
                    "presets_minutes": [0, 20, 20, 900, "30"],
                    "fallback_seconds": {"review": -2},
                },
                "resume": {"checkpoint_seconds": 0},
                "return_ramp": {"absence_days": 0, "suggestion_count": 99},
                "backtrack": {"history_limit": 1},
                "mind_notes": {"maximum_active_per_topic": 99},
                "recovery": {
                    "default_mode": "opaque",
                    "max_quick": 99,
                    "deck_name_pattern": "No placeholder",
                },
            }
        )
        self.assertTrue(config.enabled)
        self.assertEqual(config.general.theme, "auto")
        self.assertTrue(config.general.keyboard_shortcuts)
        self.assertEqual(config.context.side, "right")
        self.assertEqual(config.context.width, 480)
        self.assertEqual(config.context.collapse_shortcut, "Escape")
        self.assertEqual(config.hud.placement, "bottom_left")
        self.assertEqual(config.time_machine.presets_minutes, (20,))
        self.assertEqual(config.time_machine.fallback_seconds.review, 1.0)
        self.assertEqual(config.resume.checkpoint_seconds, 5)
        self.assertEqual(config.return_ramp.absence_days, 1)
        self.assertEqual(config.return_ramp.suggestion_count, 5)
        self.assertEqual(config.backtrack.history_limit, 2)
        self.assertEqual(config.mind_notes.maximum_active_per_topic, 10)
        self.assertEqual(config.recovery.default_mode, "standard")
        self.assertEqual(config.recovery.max_quick, 8)
        self.assertIn("{topic}", config.recovery.deck_name_pattern)

    def test_round_trip_preserves_module_independence(self) -> None:
        flags = ModuleFlags(
            context=False,
            recovery=True,
            time_machine=False,
            hud=True,
            resume=False,
            topic_health=True,
            home_panel=False,
        )
        original = replace(VellumConfig(), modules=flags)
        restored = VellumConfig.from_mapping(original.to_mapping())
        self.assertEqual(restored, original)


if __name__ == "__main__":
    unittest.main()
