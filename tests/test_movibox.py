"""movibox: what it lists, what it skips, and how a link is shaped.

No network here. The three decisions worth pinning are the film/show filter,
the home-row taxonomy, and the fact that a play/download request is built
with the player route as its referer — that referer is the whole gate.
"""

import unittest

from nkiri import movibox


class WantedTest(unittest.TestCase):
    """subjectType 1 is a film, 2 a series, 6 music and stage shows."""

    def test_films_and_series_pass(self):
        for kind in (1, 2):
            self.assertTrue(movibox._wanted(
                {"subjectType": kind, "detailPath": "x-abc"}), kind)

    def test_music_and_stage_shows_stay_out(self):
        self.assertFalse(movibox._wanted(
            {"subjectType": 6, "detailPath": "song-abc"}))

    def test_adult_stays_out(self):
        self.assertFalse(movibox._wanted(
            {"subjectType": 1, "detailPath": "x-abc", "isPornographic": True}))

    def test_a_subject_without_a_path_is_not_a_card(self):
        self.assertFalse(movibox._wanted({"subjectType": 1, "detailPath": ""}))


class ItemTest(unittest.TestCase):
    def test_the_card_is_keyed_by_its_detail_path(self):
        item = movibox._item({"subjectType": 2, "detailPath": "the-body-swzR",
                              "title": "The Body", "releaseDate": "2023-01-02",
                              "cover": {"url": "https://pbcdnw.aoneroom.com/a.jpg"}})
        self.assertEqual(item["id"], "the-body-swzR")
        self.assertEqual(item["date"], "2023-01-02")
        self.assertEqual(item["poster"], "https://pbcdnw.aoneroom.com/a.jpg")
        self.assertTrue(item["url"].endswith("/movies/the-body-swzR"))

    def test_the_original_cover_is_used(self):
        """Not a resized copy: a 535x755 poster must stay portrait."""
        item = movibox._item({"subjectType": 1, "detailPath": "a-b",
                              "cover": {"url": "https://pbcdnw.aoneroom.com/i/o.jpg",
                                        "width": 535, "height": 755}})
        self.assertEqual(item["poster"], "https://pbcdnw.aoneroom.com/i/o.jpg")


class SectionTest(unittest.TestCase):
    """The home rows are the taxonomy, because there is no genre endpoint."""

    def setUp(self):
        self._saved = movibox._home
        movibox._home = lambda: {"operatingList": [
            {"type": "BANNER", "title": "Banner_Africa", "opId": "1",
             "subjects": [{"subjectType": 1, "detailPath": "b-1"}]},
            {"type": "SUBJECTS_MOVIE", "title": "Popular Series", "opId": "42",
             "subjects": [{"subjectType": 2, "detailPath": "s-1"},
                          {"subjectType": 2, "detailPath": "s-2"}]},
            {"type": "SUBJECTS_MOVIE", "title": "Music Videos", "opId": "43",
             "subjects": [{"subjectType": 6, "detailPath": "m-1"}]},
            {"type": "SPORT_LIVE", "title": "Football Live", "opId": "44",
             "subjects": []},
        ]}

    def tearDown(self):
        movibox._home = self._saved

    def test_only_subject_rows_become_chips(self):
        chips = movibox.menu()
        self.assertEqual([c["name"] for c in chips], ["Popular Series"])
        self.assertEqual(chips[0]["slug"], "42")
        self.assertEqual(chips[0]["count"], 2)

    def test_a_row_of_music_is_not_a_chip(self):
        """Its subjects are all filtered out, so the row is dropped, not empty."""
        self.assertNotIn("Music Videos", [c["name"] for c in movibox.menu()])

    def test_browse_returns_that_rows_subjects(self):
        page = movibox.browse("42", limit=10)
        self.assertEqual([i["id"] for i in page["items"]], ["s-1", "s-2"])
        self.assertEqual(page["total_pages"], 1)

    def test_an_unknown_row_is_empty(self):
        self.assertEqual(movibox.browse("nope")["items"], [])

    def test_latest_flattens_the_rows(self):
        page = movibox.latest(limit=10)
        self.assertEqual([i["id"] for i in page["items"]], ["s-1", "s-2"])


class EpisodesTest(unittest.TestCase):
    def test_a_film_answers_to_season_zero(self):
        """A film is se=0 ep=0: asking for se=1 returns nothing at all."""
        self.assertEqual(movibox._episodes([{"se": 0, "maxEp": 0}]), [(0, 0)])

    def test_a_season_is_one_row_per_episode(self):
        self.assertEqual(movibox._episodes([{"se": 2, "maxEp": 3}]),
                         [(2, 1), (2, 2), (2, 3)])

    def test_no_season_at_all_still_asks_once(self):
        self.assertEqual(movibox._episodes([]), [(0, 0)])


class LinkTest(unittest.TestCase):
    def test_a_signed_mp4_is_the_file(self):
        url = ("https://bcdnw.hakunaymatata.com/bt/abc.mp4"
               "?sign=deadbeef&t=1794672380")
        self.assertTrue(movibox.file_host_allowed(url))
        self.assertEqual(movibox.resolve_info(url)["direct"], url)

    def test_the_cdn_wants_a_movibox_referer(self):
        url = "https://bcdnxw.hakunaymatata.com/bt/abc.mp4?sign=x"
        self.assertEqual(movibox.file_referer(url), "https://movibox.net/")

    def test_another_host_gets_no_referer(self):
        self.assertIsNone(movibox.file_referer("https://downloadwella.com/x.mkv"))

    def test_a_lookalike_host_is_not_the_cdn(self):
        self.assertFalse(movibox.file_host_allowed(
            "https://hakunaymatata.com.evil.test/abc.mp4"))

    def test_there_is_no_chain_to_walk(self):
        self.assertFalse(movibox.resolve_host_allowed(
            "https://bcdnw.hakunaymatata.com/bt/abc.mp4"))


class RefTest(unittest.TestCase):
    def test_a_bare_detail_path_passes_through(self):
        self.assertEqual(movibox.parse_ref("the-body-swzR"), "the-body-swzR")

    def test_a_url_yields_its_last_segment(self):
        self.assertEqual(
            movibox.parse_ref("https://movibox.net/movies/the-body-swzR?id=1"),
            "the-body-swzR")

    def test_nothing_is_none(self):
        self.assertIsNone(movibox.parse_ref("  "))


class PlayRouteTest(unittest.TestCase):
    """The referer is the gate: without this exact prefix the API answers
    hasResource:false and every stream list is empty."""

    def test_the_player_referer_is_a_movies_route(self):
        self.assertTrue(movibox.PLAY_ROUTE.startswith("https://movibox.net/movies/"))


if __name__ == "__main__":
    unittest.main()
