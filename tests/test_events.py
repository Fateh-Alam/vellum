import logging
import unittest

from vellum.core.events import EventBus


class EventBusTests(unittest.TestCase):
    def test_handlers_run_in_order_and_can_unsubscribe(self) -> None:
        calls: list[str] = []
        bus = EventBus()
        unsubscribe = bus.subscribe("card_shown", lambda: calls.append("first"))
        bus.subscribe("card_shown", lambda: calls.append("second"))
        bus.emit("card_shown")
        unsubscribe()
        bus.emit("card_shown")
        self.assertEqual(calls, ["first", "second", "second"])

    def test_bad_handler_does_not_block_later_handlers(self) -> None:
        calls: list[str] = []
        logger = logging.getLogger("vellum.tests.events")
        logger.addHandler(logging.NullHandler())
        bus = EventBus(logger=logger)

        def fail() -> None:
            raise RuntimeError("expected test failure")

        bus.subscribe("card_answered", fail)
        bus.subscribe("card_answered", lambda: calls.append("survived"))
        bus.emit("card_answered")
        self.assertEqual(calls, ["survived"])


if __name__ == "__main__":
    unittest.main()
