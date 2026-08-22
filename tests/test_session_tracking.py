from pathlib import Path
import tempfile
import unittest

from vellum.core.db import Database
from vellum.features.session_tracking import SessionTrackingModule
from vellum.sessions.manager import SessionManager
from vellum.sessions.models import SessionOrigin, SessionStatus
from vellum.sessions.repository import SessionRepository


class Queue:
    def __init__(self, remaining: int) -> None:
        self.new_count = remaining
        self.learning_count = 0
        self.review_count = 0


class Scheduler:
    def __init__(self, remaining: int) -> None:
        self.remaining = remaining

    def get_queued_cards(self, fetch_limit: int) -> Queue:
        assert fetch_limit == 1
        return Queue(self.remaining)


class Collection:
    def __init__(self, remaining: int) -> None:
        self.sched = Scheduler(remaining)


class DeferredProgress:
    def __init__(self) -> None:
        self.calls: list[tuple[int, object, bool]] = []

    def single_shot(self, delay: int, callback: object, requires_collection: bool) -> None:
        self.calls.append((delay, callback, requires_collection))


class DeferredMainWindow:
    def __init__(self) -> None:
        self.progress = DeferredProgress()


class TimingRecorder:
    def __init__(self) -> None:
        self.records: list[tuple[object, int, str]] = []

    def record(self, bucket: object, duration_ms: int, session_id: str) -> None:
        self.records.append((bucket, duration_ms, session_id))


class SessionTrackingCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "vellum.sqlite3")
        self.database.migrate()
        self.manager = SessionManager(
            SessionRepository(self.database), id_factory=lambda: "tracking"
        )
        self.tracking = SessionTrackingModule(self.manager, topics=None)  # type: ignore[arg-type]

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_exhausted_normal_queue_completes(self) -> None:
        self.manager.start()
        self.tracking._collection = Collection(0)
        self.tracking._reviewer_ended()
        self.assertEqual(self.manager.current.status, SessionStatus.COMPLETED)

    def test_early_exit_interrupts(self) -> None:
        self.manager.start()
        self.tracking._collection = Collection(3)
        self.tracking._reviewer_ended()
        self.assertEqual(self.manager.current.status, SessionStatus.INTERRUPTED)

    def test_recovery_waits_for_filtered_deck_cleanup(self) -> None:
        self.manager.start(origin=SessionOrigin.RECOVERY)
        self.tracking._collection = Collection(0)
        self.tracking._reviewer_ended()
        self.assertEqual(self.manager.current.status, SessionStatus.INTERRUPTED)

    def test_time_machine_waits_for_filtered_deck_cleanup(self) -> None:
        self.manager.start(origin=SessionOrigin.TIME_MACHINE)
        self.tracking._collection = Collection(0)
        self.tracking._reviewer_ended()
        self.assertEqual(self.manager.current.status, SessionStatus.INTERRUPTED)

    def test_timing_aggregation_is_deferred_past_next_card_hook(self) -> None:
        mw = DeferredMainWindow()
        timing = TimingRecorder()
        tracking = SessionTrackingModule(
            self.manager,
            topics=None,  # type: ignore[arg-type]
            timing=timing,  # type: ignore[arg-type]
            mw=mw,
        )

        from vellum.timing.models import TimingBucket

        tracking._record_timing_after_transition(
            TimingBucket.REVIEW,
            1200,
            "tracking",
        )

        self.assertEqual(timing.records, [])
        self.assertEqual(mw.progress.calls[0][0], 25)
        callback = mw.progress.calls[0][1]
        callback()  # type: ignore[operator]
        self.assertEqual(
            timing.records,
            [(TimingBucket.REVIEW, 1200, "tracking")],
        )


if __name__ == "__main__":
    unittest.main()
