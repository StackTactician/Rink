"""Adding a source is a package, not a scattered edit.

These tests are the guard on that claim. They check every registered source
answers the same questions, and they add a fake fourth source to prove the
registry and the toggle pick it up without a single change outside its own
module.
"""

import os
import re
import unittest

from rink import sources

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: the interface a source package has to provide, and what the registry reads
META_KEYS = ("id", "label", "site", "kind", "aliases", "can_size",
             "has_formats", "poster_aspect", "image_hosts")
CALLABLE = ("chips", "formats", "latest", "browse", "search", "parse_ref",
            "post_view", "resolve_info", "size_info", "file_host_allowed",
            "resolve_host_allowed", "file_referer", "clear_cache")


class ContractTest(unittest.TestCase):
    def test_every_source_answers_the_same_questions(self):
        for module in sources._MODULES:
            for key in META_KEYS:
                self.assertIn(key, module.META, f"{module.__name__}.META[{key}]")
            for name in CALLABLE:
                self.assertTrue(callable(getattr(module, name, None)),
                                f"{module.__name__}.{name}()")

    def test_ids_are_unique_and_normalise_to_themselves(self):
        ids = [m.META["id"] for m in sources._MODULES]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in sources.source_list():
            self.assertEqual(sources.norm(entry["id"]), entry["id"])
            self.assertIs(sources.mod(entry["id"]), sources.mod(entry["id"]))

    def test_an_alias_reaches_the_same_package(self):
        for module in sources._MODULES:
            for alias in module.META["aliases"]:
                self.assertIs(sources.mod(alias), module, alias)

    def test_the_registry_names_no_source(self):
        """No `if src == ...` chain: the dispatch is the table."""
        path = os.path.join(ROOT, "rink", "sources", "__init__.py")
        with open(path, encoding="utf-8") as f:
            body = f.read()
        for module in sources._MODULES:
            src_id = module.META["id"]
            self.assertNotIn(f'== "{src_id}"', body)
            self.assertNotIn(f"== {src_id!r}", body)
        self.assertNotIn("JAROCKS:", body)


class FakeSource:
    """A fourth source, written the way a real one would be."""

    META = {
        "id": "fakesrc", "label": "Fake", "site": "https://fake.example",
        "kind": "category",
        "aliases": ("fake", "fake.example"),
        "can_size": True, "has_formats": False, "poster_aspect": "2/3",
        "image_hosts": ("fake.example",),
        "file_tags": ("fake.example",),
    }
    __name__ = "rink.sources.fakesrc"
    calls = []

    @classmethod
    def chips(cls):
        return [{"slug": "all", "name": "All", "count": 1}]

    @classmethod
    def formats(cls):
        return []

    @classmethod
    def latest(cls, limit=24, page=1):
        cls.calls.append("latest")
        return {"items": [{"id": "f1", "title": "Fake"}], "page": page,
                "per_page": limit, "total": 1, "total_pages": 1}

    @classmethod
    def browse(cls, slug="", limit=24, page=1, cat=""):
        cls.calls.append("browse")
        return cls.latest(limit, page)

    @classmethod
    def search(cls, query, limit=24, page=1):
        cls.calls.append("search")
        return cls.latest(limit, page)

    @classmethod
    def parse_ref(cls, ref):
        return "f1"

    @classmethod
    def post_view(cls, ref):
        return {"id": ref, "title": "Fake", "links": []}

    @classmethod
    def resolve_info(cls, url):
        cls.calls.append("resolve")
        return {"direct": url, "name": "fake.mp4", "size": None}

    @classmethod
    def size_info(cls, url):
        cls.calls.append("size")
        return {"size": "1 MB", "bytes": 1024 * 1024}

    @classmethod
    def file_host_allowed(cls, url):
        return "fake.example" in (url or "")

    @classmethod
    def resolve_host_allowed(cls, url):
        return cls.file_host_allowed(url)

    @classmethod
    def file_referer(cls, url):
        return None

    @classmethod
    def clear_cache(cls):
        cls.calls.append("clear")


class FourthSourceTest(unittest.TestCase):
    """Add a source, change nothing else, and watch it appear everywhere."""

    def setUp(self):
        self._saved = sources._MODULES
        FakeSource.calls = []
        sources._MODULES = self._saved + (FakeSource,)
        # the lookup tables are derived at import, so rebuild them the way a
        # real module would have been present for
        sources.SOURCES = tuple((m.META["id"], m.META) for m in sources._MODULES)
        sources._ALIASES = {a: m.META["id"] for m in sources._MODULES
                            for a in m.META["aliases"]}
        sources._ALIASES.update({m.META["id"]: m.META["id"]
                                 for m in sources._MODULES})

    def tearDown(self):
        sources._MODULES = self._saved
        sources.SOURCES = tuple((m.META["id"], m.META) for m in sources._MODULES)
        sources._ALIASES = {a: m.META["id"] for m in sources._MODULES
                            for a in m.META["aliases"]}
        sources._ALIASES.update({m.META["id"]: m.META["id"]
                                 for m in sources._MODULES})

    def test_it_appears_in_the_toggle_with_what_it_can_do(self):
        listed = {s["id"]: s for s in sources.source_list()}
        self.assertIn("fakesrc", listed)
        self.assertTrue(listed["fakesrc"]["can_size"])
        self.assertEqual(listed["fakesrc"]["poster_aspect"], "2/3")

    def test_the_registry_routes_to_it_by_id_and_by_alias(self):
        self.assertEqual(sources.norm("fake"), "fakesrc")
        self.assertEqual(sources.latest("fakesrc")["items"][0]["id"], "f1")
        self.assertEqual(sources.latest("fake.example")["items"][0]["id"], "f1")
        self.assertIn("latest", FakeSource.calls)

    def test_its_own_menu_is_its_own_taxonomy(self):
        self.assertEqual(sources.menu("fake")["kind"], "category")
        self.assertEqual(sources.menu("fake")["chips"][0]["slug"], "all")
        self.assertEqual(sources.menu("fake")["formats"], [])

    def test_its_hosts_answer_for_itself(self):
        url = "https://fake.example/x.mp4"
        self.assertTrue(sources.file_allowed(url))
        self.assertTrue(sources.resolve_allowed(url))
        self.assertEqual(sources.size("nkiri", url)["size"], "1 MB")

    def test_a_source_that_cannot_size_says_so_and_is_not_asked(self):
        class NoSize(FakeSource):
            META = dict(FakeSource.META, id="nosize", aliases=("nosize",),
                        can_size=False, image_hosts=("nosize.example",))
            __name__ = "rink.sources.nosize"

            @classmethod
            def file_host_allowed(cls, url):
                return "nosize.example" in (url or "")

        sources._MODULES = sources._MODULES + (NoSize,)
        self.assertEqual(sources.size("nosize", "https://nosize.example/x.mp4"),
                         {"size": None, "bytes": None})
        self.assertNotIn("size", NoSize.calls)

    def test_clear_cache_reaches_it(self):
        sources.clear_cache()
        self.assertIn("clear", FakeSource.calls)


class NoSourceKnowsAnotherTest(unittest.TestCase):
    """A source package must not import a sibling: they are peers."""

    def test_no_adapter_imports_a_sibling_source(self):
        base = os.path.join(ROOT, "rink", "sources")
        ids = [m.META["id"] for m in sources._MODULES]
        pkg_names = [d for d in os.listdir(base)
                     if os.path.isdir(os.path.join(base, d))]
        for pkg in pkg_names:
            folder = os.path.join(base, pkg)
            for name in os.listdir(folder):
                if not name.endswith(".py"):
                    continue
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    body = f.read()
                for other in pkg_names:
                    if other == pkg:
                        continue
                    self.assertNotIn(f"from ..{other}", body,
                                     f"{pkg}/{name} imports {other}")
                    self.assertNotIn(f"import {other}", body,
                                     f"{pkg}/{name} imports {other}")
        self.assertTrue(ids)


if __name__ == "__main__":
    unittest.main()
