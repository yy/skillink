"""Check catalog provenance, variant selection, and safe HTML rendering."""

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

with patch.object(
    sys, "path", [str(Path(__file__).resolve().parents[1] / "bin"), *sys.path]
):
    listing = importlib.import_module("list_skills")


class CatalogTests(unittest.TestCase):
    def test_private_catalog_write_preserves_unrelated_files_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "catalog.html"
            content = listing.HTML_MARKER + "private instructions"
            listing.write_html(output, content)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            output.chmod(0o644)
            listing.write_html(output, content + " updated")
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            output.write_text("unrelated document")
            with self.assertRaises(ValueError):
                listing.write_html(output, content)
            self.assertEqual(output.read_text(), "unrelated document")
            link = root / "link.html"
            link.symlink_to(output)
            with self.assertRaises(ValueError):
                listing.write_html(link, content)
            self.assertEqual(output.read_text(), "unrelated document")

    def test_sources_exclusions_and_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for source, name in [("personal", "alpha"), ("shared", "beta")]:
                skill = root / source / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: About {name}\n---\nInstructions.\n"
                )
            (root / "shared/beta/variants").mkdir()
            (root / "shared/beta/variants/detailed.md").write_text(
                "---\nname: beta\ndescription: Guided beta\n---\nExplicit steps.\n"
            )
            manifest = root / "skills.toml"
            manifest.write_text(
                "format_version = 1\n[sources]\n"
                'personal = "personal"\nshared = "shared"\n'
                '[profiles.frontier]\ntarget = "out/frontier"\n'
                'include = ["personal/*", "shared/*"]\n'
                '[profiles.local]\ntarget = "out/local"\n'
                'include = ["personal/*", "shared/*"]\nexclude = ["personal/alpha"]\n'
                '[profiles.local.variants]\n"shared/beta" = "detailed"\n'
            )
            rows = listing.catalog(manifest)
            self.assertEqual(
                [(r["id"], r["variant"], r["profiles"]) for r in rows],
                [
                    ("personal/alpha", "canonical", ["frontier"]),
                    ("shared/beta", "canonical", ["frontier"]),
                    ("shared/beta", "detailed", ["local"]),
                ],
            )
            local = listing.catalog(manifest, "local")
            self.assertEqual(len(local), 1)
            self.assertEqual(local[0]["description"], "Guided beta")
            self.assertFalse((root / "out").exists())

    def test_html_escapes_skill_content_and_keeps_template_tokens_literal(self):
        row = {
            "id": "personal/alpha",
            "name": "alpha",
            "source": "personal",
            "variant": "canonical",
            "profiles": ["frontier"],
            "description": '<script>alert("x")</script>',
            "instructions": "{{rows}} <img src=x onerror=alert(1)>",
            "path": "/tmp/alpha/SKILL.md",
        }
        html = listing.html_catalog([row], Path("/tmp/skills.toml"))
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("{{rows}} &lt;img", html)
        self.assertEqual(html.count("<tr data-source="), 1)


if __name__ == "__main__":
    unittest.main()
