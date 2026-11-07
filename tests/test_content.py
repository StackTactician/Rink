import unittest

from nkiri.content import (
    display_label,
    extract_synopsis,
    find_download_links,
    parse_post_view,
)

HTML = """
<p>Intro</p>
<h3>Download Episode 1</h3>
<a href="https://downloadwella.com/abc/file.mkv.html">Download Episode</a>
<a href="https://thenkiri.com/some-page/">internal</a>
<a href="#top">top</a>
<h3>Download Episode 2</h3>
<a href="https://downloadwella.com/def/file2.mkv.html">Download Episode</a>
<a href="https://downloadwella.com/abc/file.mkv.html">duplicate</a>
<h2>Synopsis</h2>
<p>An assassin retires.</p>
"""


class ContentTest(unittest.TestCase):
    def test_find_download_links(self):
        links = find_download_links(HTML)
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]["label"], "Download Episode 1")
        self.assertEqual(links[1]["label"], "Download Episode 2")
        self.assertTrue(links[0]["url"].startswith("https://downloadwella.com/"))

    def test_duplicates_dropped(self):
        urls = [l["url"] for l in find_download_links(HTML)]
        self.assertEqual(len(urls), len(set(urls)))

    def test_display_label(self):
        self.assertEqual(display_label({"label": "Episode 3", "text": "x"}), "Episode 3")
        self.assertEqual(display_label({"label": "Download", "text": "720p"}), "720p")

    def test_extract_synopsis(self):
        self.assertEqual(extract_synopsis(HTML), "An assassin retires.")

    def test_extract_synopsis_missing(self):
        self.assertEqual(extract_synopsis("<p>nothing</p>"), "")

    def test_parse_post_view(self):
        post = {
            "id": 1,
            "title": "T",
            "link": "https://thenkiri.com/t/",
            "date": "2026-11-07T10:00:00",
            "poster": "p.jpg",
            "content": {"rendered": HTML},
        }
        view = parse_post_view(post)
        self.assertEqual(view["date"], "2026-11-07")
        self.assertEqual(view["poster"], "p.jpg")
        self.assertEqual(len(view["links"]), 2)
        self.assertEqual(view["synopsis"], "An assassin retires.")


if __name__ == "__main__":
    unittest.main()
