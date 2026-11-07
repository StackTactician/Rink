import unittest

from nkiri.refs import parse_ref


class RefsTest(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(parse_ref("171585"), 171585)
        self.assertEqual(parse_ref(" 171585 "), 171585)

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_ref(""))
        self.assertIsNone(parse_ref(None))
        self.assertIsNone(parse_ref("https://nope.example/x"))


if __name__ == "__main__":
    unittest.main()
