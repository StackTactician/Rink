import unittest

from nkiri.text import clean_title, human_size, strip_tags


class TextTest(unittest.TestCase):
    def test_strip_tags_unescapes(self):
        self.assertEqual(strip_tags("<p>A &amp; B</p>"), "A & B")

    def test_strip_tags_none(self):
        self.assertEqual(strip_tags(None), "")

    def test_clean_title_splits_pipe(self):
        self.assertEqual(
            clean_title("Resident Evil (2026) | Download Hollywood Movie"),
            "Resident Evil (2026)")

    def test_clean_title_strips_inner_tags(self):
        self.assertEqual(clean_title("<b>Title</b> | x"), "Title")

    def test_human_size(self):
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(512), "512 B")
        self.assertEqual(human_size(1024), "1.0 KB")
        self.assertEqual(human_size(1024 ** 2), "1.0 MB")


if __name__ == "__main__":
    unittest.main()
