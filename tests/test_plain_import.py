import unittest


class ImportTests(unittest.TestCase):
    def test_package_is_safe_without_anki(self) -> None:
        import vellum

        self.assertIsNone(vellum.APP)


if __name__ == "__main__":
    unittest.main()
