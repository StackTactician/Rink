"""The 9jarocks category filter: what the source lists, and what search keeps.

No network here — the per-post lookups are served from the cache the search
path reads, so these tests pin the decisions rather than the plumbing.
"""

import unittest

from nkiri import jarocks


class FilmOrShowTest(unittest.TestCase):
    def test_allowlisted_categories_pass(self):
        for slug in ("hollywood-movie", "korean-drama", "anime",
                     "spanish-drama-telenovela", "nollywood-tv-series"):
            self.assertTrue(jarocks._is_film_or_show(slug), slug)

    def test_adult_is_not_listed(self):
        """Its own category and the bigger 18+ bucket both stay out."""
        self.assertFalse(jarocks._is_film_or_show("adult"))
        self.assertFalse(jarocks._is_film_or_show("18-section"))

    def test_other_non_film_categories_stay_out(self):
        for slug in ("gist", "news", "sports", "sports-highlights",
                     "foreign-music", "mp3download", "whatsapp-stories",
                     "pro-wrestling-fighting-sports", "uncategorized"):
            self.assertFalse(jarocks._is_film_or_show(slug), slug)

    def test_a_language_added_later_still_passes(self):
        self.assertTrue(jarocks._is_film_or_show("german-drama"))
        self.assertTrue(jarocks._is_film_or_show("somali-movies"))


class TitleFallbackTest(unittest.TestCase):
    """What decides when a hit's category cannot be read."""

    def test_music_and_gist_prefixes_are_dropped(self):
        for title in ("Music: Burna Boy - City Boys",
                      "Music Box: Asake - Lonely At The Top",
                      "Video: Spyro Ft. Tiwa Savage - Who Is Your Guy",
                      "MP3: Rema - Calm Down",
                      "Lyrics: Omah Lay - Soso"):
            self.assertFalse(jarocks._looks_like_film(title), title)

    def test_music_hints_without_a_year_are_dropped(self):
        self.assertFalse(jarocks._looks_like_film("Asake - Lonely At The Top (Remix)"))
        self.assertFalse(jarocks._looks_like_film("New Gospel Song Wey Dey Trend"))

    def test_a_year_outranks_both_screens(self):
        self.assertTrue(jarocks._looks_like_film("Music (2021)"))
        self.assertTrue(jarocks._looks_like_film("The Clark Sisters: Gospel (2020)"))

    def test_films_and_shows_pass(self):
        for title in ("Mercy (2026)", "Really Love",
                      "No Mercy Season 1 (Complete) (Korean Drama)"):
            self.assertTrue(jarocks._looks_like_film(title), title)

    def test_uncategorized_is_not_a_listing(self):
        self.assertFalse(jarocks._looks_like_film(
            "Something (2020)", "https://9jarocks.net/uncategorized/x.html"))


class ListedFlagsTest(unittest.TestCase):
    def setUp(self):
        jarocks._post_cat_cache.clear()

    def tearDown(self):
        jarocks._post_cat_cache.clear()

    def flags(self, order, cards):
        return jarocks._listed_flags(order, cards)

    def test_known_category_decides(self):
        jarocks._post_cat_cache.set(1, ("adult", "videodownload"))
        jarocks._post_cat_cache.set(2, ("korean-drama", "videodownload"))
        got = self.flags([1, 2], {1: {"title": "X (2024)", "url": "u"},
                                  2: {"title": "Y (2024)", "url": "u"}})
        self.assertEqual(got, {1: False, 2: True})

    def test_unknown_category_falls_back_to_the_title(self):
        jarocks._post_cat_cache.set(3, ())
        cards = {3: {"title": "Music: Burna Boy - City Boys", "url": "u"},
                 4: {"title": "Mercy (2026)", "url": "u"}}
        jarocks._post_cat_cache.set(4, ())
        self.assertEqual(self.flags([3, 4], cards), {3: False, 4: True})

    def test_order_is_preserved(self):
        for pid in (5, 6, 7):
            jarocks._post_cat_cache.set(pid, ("anime", "videodownload"))
        cards = {pid: {"title": "T (2020)", "url": "u"} for pid in (5, 6, 7)}
        self.assertEqual(list(self.flags([7, 5, 6], cards)), [7, 5, 6])

    def test_empty_order_is_free(self):
        self.assertEqual(self.flags([], {}), {})


class EpisodeLabelTest(unittest.TestCase):
    """Some posts name each row, others print one season header above rows
    whose only identifier is inside the filename."""

    def label(self, heading, url):
        return jarocks._label_for(heading, url)

    def test_a_season_header_yields_to_the_filename(self):
        url = ("https://loadedfiles.net/27789ff5/Name.That.Tune.S06E02"
               ".540p.X265.AAC.[9jaRocks.Com].mkv")
        self.assertEqual(self.label("SEASON 6", url), "S06E02")

    def test_an_episode_label_is_kept(self):
        url = ("https://loadedfiles.net/ecc02930/The.Terrors.Of.Jordan"
               ".Mendoza.S01E01.540p.mkv")
        self.assertEqual(self.label("Episode 1", url), "Episode 1")

    def test_a_three_digit_episode_keeps_its_digits(self):
        url = "https://loadedfiles.net/x/Some.Show.S02E104.480p.mkv"
        self.assertEqual(self.label("", url), "S02E104")

    def test_nothing_to_go_on(self):
        self.assertEqual(self.label("", "https://loadedfiles.net/x/file.mkv"), "")
        self.assertEqual(self.label("SEASON 6", "https://loadedfiles.net/x/a.mkv"),
                         "SEASON 6")

    def test_percent_encoded_filenames_still_match(self):
        url = "https://loadedfiles.net/x/Some%20Show%20S03E07.720p.mkv"
        self.assertEqual(self.label("", url), "S03E07")

    def test_single_letter_season_and_episode(self):
        url = "https://loadedfiles.net/x/a.S1E2.mkv"
        self.assertEqual(self.label("", url), "S01E02")


class SizeParseTest(unittest.TestCase):
    """The file host prints the size beside the filename, and a plan blurb
    prints a bigger number further down the same page."""

    def parse(self, page):
        found = jarocks._SIZE_AFTER_FILE_RE.search(page)
        if not found:
            return None
        return f"{found.group(1)} {found.group(2).upper()}"

    def test_size_after_the_file_extension(self):
        page = ("Name.That.Tune.S06E02.540p.X265.AAC.[9jaRocks.Com].mkv"
                " 200.55 MB <a href='x'>Download</a>")
        self.assertEqual(self.parse(page), "200.55 MB")

    def test_a_plan_limit_is_not_a_file_size(self):
        page = ("Upload files up to 3.79 GB in size."
                "<div>Some.Series.S01E01.540p.mkv 195.45 MB</div>")
        self.assertEqual(self.parse(page), "195.45 MB")

    def test_no_size_on_the_page(self):
        self.assertIsNone(self.parse("<html>nothing to see</html>"))

    def test_parse_size_agrees(self):
        from nkiri.text import parse_size
        self.assertEqual(parse_size("200.55 MB"), 210291916)


class CardParseTest(unittest.TestCase):
    PAGE = (
        '<li class="post-item is-trending">'
        '<a aria-label="Mercy (2026)" href="https://9jarocks.net/videodownload/'
        'mercy-id375773.html" class="post-thumb">'
        '<img src="https://9jarocks.net/wp-content/uploads/2026/02/m.jpg" /></a>'
        '</li>'
        '<li class="post-item">'
        '<a aria-label="Music: Burna Boy - City Boys" href="https://9jarocks.net/'
        'videodownload/city-boys-id375700.html">'
        '<img src="https://9jarocks.net/wp-content/uploads/2026/02/c.jpg" /></a>'
        '</li>'
    )

    def test_cards_keep_the_public_shape(self):
        cards = jarocks._cards(self.PAGE)
        self.assertEqual([c["id"] for c in cards], [375773, 375700])
        for card in cards:
            self.assertEqual(set(card), {"id", "title", "url", "date", "poster"})

    def test_listing_thumbnail_is_replaced_by_the_original(self):
        """A -390x220 on a category page is a crop of the real poster: the
        bottom third, usually the title, is gone."""
        url = ("https://9jarocks.net/wp-content/uploads/2026/02/"
               "Falling_Poster-390x220.jpg")
        self.assertEqual(
            jarocks._full_poster(url),
            "https://9jarocks.net/wp-content/uploads/2026/02/Falling_Poster.jpg")

    def test_a_suffix_that_is_not_a_size_is_left_alone(self):
        for url in ("https://9jarocks.net/wp-content/uploads/2026/02/"
                    "sodRW36uEDHjv8l1WhYUNDvnIK6.jpg",
                    "https://9jarocks.net/wp-content/uploads/2026/02/Poster.webp",
                    ""):
            self.assertEqual(jarocks._full_poster(url), url)

    def test_rating_widget_numbers_are_stripped(self):
        page = ('<li class="post-item"><a aria-label="Mercy (2026) 4.6 (9)" '
                'href="https://9jarocks.net/videodownload/m-id1.html">'
                '<img src="https://9jarocks.net/wp-content/uploads/x.jpg" /></a></li>')
        self.assertEqual(jarocks._cards(page)[0]["title"], "Mercy (2026)")


if __name__ == "__main__":
    unittest.main()
