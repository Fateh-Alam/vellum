from __future__ import annotations

import json
from pathlib import Path
import unittest

from vellum.core.release import (
    VELLUM_HOMEPAGE,
    VELLUM_MIN_ANKI_VERSION,
    VELLUM_TESTED_ANKI_VERSION,
    VELLUM_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]


class ReleaseIdentityTests(unittest.TestCase):
    def test_manifest_matches_runtime_release_identity(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["human_version"], VELLUM_VERSION)
        self.assertEqual(manifest["homepage"], VELLUM_HOMEPAGE)
        self.assertEqual(manifest["min_point_version"], VELLUM_MIN_ANKI_VERSION)
        self.assertEqual(manifest["max_point_version"], VELLUM_TESTED_ANKI_VERSION)

    def test_release_is_not_marked_as_development(self) -> None:
        self.assertNotIn("dev", VELLUM_VERSION.lower())
