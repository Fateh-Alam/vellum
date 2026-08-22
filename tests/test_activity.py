from pathlib import Path
import tempfile
import unittest

from vellum.continuity.activity import ActivityRepository
from vellum.core.db import Database


class ActivityRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.directory.name) / "vellum.sqlite3")
        self.database.migrate()

    def tearDown(self) -> None:
        self.database.close()
        self.directory.cleanup()

    def test_first_open_never_claims_a_return_ramp(self) -> None:
        repository = ActivityRepository(self.database)
        activity = repository.begin_open(1_000_000)
        self.assertIsNone(activity.absence_seconds)
        self.assertIsNone(repository.claim_ramp(1))

    def test_any_configured_day_threshold_is_honored(self) -> None:
        first = ActivityRepository(self.database)
        first.begin_open(1_000_000)
        first.finish_open(1_000_100)

        second = ActivityRepository(self.database)
        activity = second.begin_open(1_000_100 + 17 * 86400)
        self.assertEqual(activity.absence_seconds, 17 * 86400)
        self.assertFalse(second.ramp_due(18))
        self.assertTrue(second.ramp_due(17))
        self.assertIsNotNone(second.claim_ramp(17))
        self.assertIsNone(second.claim_ramp(17))

    def test_unclean_close_falls_back_to_previous_open_time(self) -> None:
        first = ActivityRepository(self.database)
        first.begin_open(500)
        second = ActivityRepository(self.database)
        activity = second.begin_open(500 + 4 * 86400)
        self.assertEqual(activity.absence_seconds, 4 * 86400)
        self.assertTrue(second.ramp_due(4))


if __name__ == "__main__":
    unittest.main()
