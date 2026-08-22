import unittest

from vellum.ui.recovery import unique_deck_name


class FakeDecks:
    def __init__(self, names=()) -> None:
        self._names = set(names)

    def id_for_name(self, name: str):
        return hash(name) if name in self._names else None


class FakeCollection:
    def __init__(self, names=()) -> None:
        self.decks = FakeDecks(names)


class RecoveryDeckNameTests(unittest.TestCase):
    def test_unused_name_is_preserved(self) -> None:
        self.assertEqual(
            unique_deck_name(FakeCollection(), "Vellum Recovery - Renal"),
            "Vellum Recovery - Renal",
        )

    def test_existing_names_receive_first_free_suffix(self) -> None:
        collection = FakeCollection(
            ("Vellum Recovery - Renal", "Vellum Recovery - Renal (2)")
        )
        self.assertEqual(
            unique_deck_name(collection, "Vellum Recovery - Renal"),
            "Vellum Recovery - Renal (3)",
        )


if __name__ == "__main__":
    unittest.main()
