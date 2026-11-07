import unittest

from nkiri.download import brand_name


class BrandNameTest(unittest.TestCase):
    def test_strips_thenkiri_tag(self):
        self.assertEqual(
            brand_name("The.Assassin.S02E01.(THENKIRI.COM).mkv"),
            "The.Assassin.S02E01.Rink.mkv")

    def test_strips_bracket_and_dot_variants(self):
        self.assertEqual(brand_name("Movie.2024.[thenkiri.com].mp4"),
                         "Movie.2024.Rink.mp4")
        self.assertEqual(brand_name("Show.S01E02.nkiri.ink.mkv"),
                         "Show.S01E02.Rink.mkv")
        self.assertEqual(brand_name("Film (NKIRI).MKV"), "Film.Rink.MKV")

    def test_keeps_episode_numbers(self):
        self.assertEqual(brand_name("Series.S03E10.1080p.(THENKIRI.COM).mkv"),
                         "Series.S03E10.1080p.Rink.mkv")

    def test_no_extension(self):
        self.assertEqual(brand_name("thenkiri-movie"), "movie.Rink")

    def test_already_branded_not_doubled(self):
        self.assertEqual(brand_name("Movie.Rink.mkv"), "Movie.Rink.mkv")

    def test_empty_stem_falls_back(self):
        self.assertEqual(brand_name("(THENKIRI.COM).mkv"), "download.Rink.mkv")


if __name__ == "__main__":
    unittest.main()
