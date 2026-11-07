import unittest
from unittest import mock

from nkiri import posts


class PaginationTest(unittest.TestCase):
    def setUp(self):
        posts._latest_cache.clear()
        posts._search_cache.clear()

    def test_page_payload_shape(self):
        p = posts.page_payload([1], 2, 5, 11, 3)
        self.assertEqual(p, {"items": [1], "page": 2, "per_page": 5,
                             "total": 11, "total_pages": 3})

    def test_latest_passes_page_and_returns_meta(self):
        rows = [{"id": 1, "title": {"rendered": "A | B"}, "link": "u",
                 "date": "2026-11-07T00:00:00", "featured_media": 0}]
        with mock.patch.object(posts, "api_get_page",
                               return_value=(rows, 7367, 307)) as m:
            res = posts.latest(24, page=2)
        m.assert_called_once()
        self.assertIn("page=2", m.call_args[0][0])
        self.assertIn("per_page=24", m.call_args[0][0])
        self.assertEqual(res["page"], 2)
        self.assertEqual(res["total"], 7367)
        self.assertEqual(res["total_pages"], 307)
        self.assertEqual(res["items"][0]["title"], "A")

    def test_out_of_range_page_is_empty_not_error(self):
        with mock.patch.object(posts, "api_get_page", side_effect=Exception("400")):
            res = posts.latest(24, page=9999)
        self.assertEqual(res["items"], [])
        self.assertEqual(res["page"], 9999)

    def _rows(self, n, title="Assassin S01"):
        return [{"id": i, "title": {"rendered": f"{title} {i}"}, "link": "u",
                 "date": "2026-11-07T00:00:00", "featured_media": 0}
                for i in range(n)]

    def test_search_fetches_once_and_pages_locally(self):
        with mock.patch.object(posts, "api_get",
                               return_value=self._rows(60)) as m:
            first = posts.search_results("assassin", 24, page=1)
            second = posts.search_results("assassin", 24, page=2)
            again = posts.search_results("assassin", 24, page=1)
        self.assertEqual(m.call_count, 1)          # pool cached per query
        self.assertEqual(len(first["items"]), 24)
        self.assertEqual(len(second["items"]), 24)
        self.assertEqual(first["items"][0]["id"], again["items"][0]["id"])
        self.assertEqual(first["total"], 60)
        self.assertEqual(first["total_pages"], 3)
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])

    def test_search_prefers_title_matches(self):
        rows = ([{"id": 1, "title": {"rendered": "Unrelated Show"},
                  "link": "u", "date": "2026-11-07T00:00:00", "featured_media": 0}]
                + [{"id": 2, "title": {"rendered": "Batman Ninja"},
                    "link": "u", "date": "2026-11-07T00:00:00", "featured_media": 0}])
        with mock.patch.object(posts, "api_get", return_value=rows):
            res = posts.search_results("batman", 24, page=1)
        self.assertEqual(res["items"][0]["title"], "Batman Ninja")
        self.assertEqual(res["total"], 1)          # body matches dropped


if __name__ == "__main__":
    unittest.main()
