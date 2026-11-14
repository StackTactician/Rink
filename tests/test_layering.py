"""The engine must not know what an interface looks like.

`sources` is the seam every client talks to, so what it returns has to make
sense to a terminal and to a browser alike. A web path appearing in a core
module is the specific bug this pins: posters used to come back as
"/api/img?u=..." from the engine, which a CLI could not do anything with.
"""

import glob
import os
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "nkiri")


def _core_sources():
    return [f for f in glob.glob(os.path.join(CORE, "*.py"))]


class CoreIsInterfaceAgnosticTest(unittest.TestCase):
    def test_no_core_module_imports_the_web_layer(self):
        for path in _core_sources():
            with open(path, encoding="utf-8") as f:
                body = f.read()
            self.assertNotIn("from .web", body, path)
            self.assertNotIn("import web", body, path)

    def test_no_core_module_returns_a_web_path(self):
        """"/api/..." belongs to the server, not to the engine.

        Comments are allowed to mention an endpoint; a string literal that
        would end up in a payload is not, so the check looks for the quoted
        form a URL would actually be built from.
        """
        offenders = []
        for path in _core_sources():
            with open(path, encoding="utf-8") as f:
                for number, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for quote in ('"/api/', "'/api/"):
                        if quote in line:
                            offenders.append(f"{os.path.basename(path)}:{number}")
        self.assertEqual(offenders, [])


class RegistryTest(unittest.TestCase):
    """One registry, and every source reachable through it."""

    def test_the_cli_goes_through_the_registry(self):
        path = os.path.join(CORE, "cli.py")
        with open(path, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("from . import sources", body)
        self.assertIn("sources.search(", body)
        self.assertIn("sources.post(", body)

    def test_every_listed_source_normalises_to_itself(self):
        from nkiri import sources
        for entry in sources.source_list():
            self.assertEqual(sources.norm(entry["id"]), entry["id"])


if __name__ == "__main__":
    unittest.main()
