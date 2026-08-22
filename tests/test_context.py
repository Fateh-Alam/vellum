import base64
import json
import unittest

from vellum.core.config import VellumConfig
from vellum.features.context import context_payload, encoded_payload
from vellum.topics.models import CardContext


def make_context(path: tuple[str, ...]) -> CardContext:
    return CardContext(
        card_id=1,
        note_id=2,
        deck_id=3,
        deck_name="Deck",
        raw_tags=(),
        topic_path=path,
        topic_source_root="#FirstAid",
        primary_topic_id="a" * 40,
        ancestor_topic_ids=("b" * 40,) if len(path) > 1 else (),
        source_badges=("First Aid",),
        state="review",
        lapses=0,
        reps=1,
        due=1,
    )


class ContextPayloadTests(unittest.TestCase):
    def test_payload_contains_no_card_content(self) -> None:
        payload = context_payload(make_context(("Renal", "ADTKD")), VellumConfig())
        self.assertEqual(payload["title"], "ADTKD")
        self.assertNotIn("cardId", payload)
        self.assertNotIn("deckName", payload)

    def test_inline_payload_is_script_safe_and_unicode_preserving(self) -> None:
        payload = context_payload(
            make_context(("Renal", "</script><script>alert('x')</script> — ADTKD")),
            VellumConfig(),
        )
        encoded = encoded_payload(payload)
        self.assertNotIn("<", encoded)
        decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
        self.assertEqual(decoded, payload)

    def test_empty_topic_has_calm_empty_state(self) -> None:
        payload = context_payload(make_context(()), VellumConfig())
        self.assertEqual(payload["title"], "No topic context")
        self.assertEqual(payload["path"], [])

    def test_behavior_and_visibility_settings_reach_webview(self) -> None:
        config = VellumConfig.from_mapping(
            {
                "context": {
                    "default_state": "remember",
                    "auto_collapse_on_new_card": True,
                    "pinned": True,
                    "show_title": False,
                    "collapse_shortcut": "Escape",
                }
            }
        )
        payload = context_payload(
            make_context(("Renal", "ADTKD")), config, phase="reviewQuestion"
        )
        self.assertEqual(payload["defaultState"], "remember")
        self.assertTrue(payload["autoCollapse"])
        self.assertTrue(payload["pinned"])
        self.assertFalse(payload["showTitle"])
        self.assertEqual(payload["phase"], "reviewQuestion")

    def test_global_shortcut_switch_disables_panel_key_handling(self) -> None:
        config = VellumConfig.from_mapping(
            {"general": {"keyboard_shortcuts": False}}
        )
        payload = context_payload(make_context(("Renal",)), config)
        self.assertEqual(payload["collapseShortcut"], "")


if __name__ == "__main__":
    unittest.main()
