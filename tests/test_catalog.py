import unittest
from unittest import mock

from nkiri import catalog


TAGS = [
    {"id": 7, "slug": "drama", "count": 3000},
    {"id": 9, "slug": "comedy", "count": 1800},
    {"id": 103, "slug": "comdey", "count": 16},
    {"id": 8, "slug": "action", "count": 1400},
]


class GenresTest(unittest.TestCase):
    def setUp(self):
        catalog.clear_cache()

    def test_variants_fold_into_one_genre(self):
        with mock.patch.object(catalog, "api_get", return_value=TAGS):
            genres = catalog.genres()
        comedy = catalog.find(genres, "comedy")
        self.assertIsNotNone(comedy)
        self.assertEqual(comedy["ids"], [9, 103])
        self.assertEqual(comedy["count"], 1816)
        # biggest first
        self.assertEqual(genres[0]["slug"], "drama")

    def test_missing_tags_are_dropped_not_faked(self):
        with mock.patch.object(catalog, "api_get", return_value=TAGS[:2]):
            genres = catalog.genres()
        self.assertIsNone(catalog.find(genres, "horror"))
        self.assertEqual([g["slug"] for g in genres], ["drama", "comedy"])

    def test_failed_lookup_yields_no_genres(self):
        with mock.patch.object(catalog, "api_get", side_effect=Exception("boom")):
            self.assertEqual(catalog.genres(), [])

    def test_browse_unknown_slug_is_empty(self):
        with mock.patch.object(catalog, "api_get", return_value=TAGS):
            res = catalog.browse("nonsense", "", 24, 1)
        self.assertEqual(res["items"], [])
        self.assertEqual(res["page"], 1)

    def test_public_strips_internal_ids(self):
        rows = [{"slug": "drama", "name": "Drama", "count": 3, "ids": [7, 95]}]
        self.assertEqual(catalog.public(rows),
                         [{"slug": "drama", "name": "Drama", "count": 3}])


if __name__ == "__main__":
    unittest.main()
