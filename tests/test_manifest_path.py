"""Verify stable configuration lookup and source paths through a config symlink."""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

with patch.object(
    sys, "path", [str(Path(__file__).resolve().parents[1] / "bin"), *sys.path]
):
    config = importlib.import_module("manifest_path")
    installer = importlib.import_module("install_skills")


class ManifestPathTests(unittest.TestCase):
    def test_precedence_and_symlink_relative_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            manifest = root / "dotfiles/skillink/skills.toml"
            manifest.parent.mkdir(parents=True)
            skill = root / "dotfiles/skills/hello"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: hello\ndescription: Say hello\n---\nGreet the user.\n"
            )
            manifest.write_text(
                'format_version = 1\n[sources]\npersonal = "../skills"\n'
                '[profiles.test]\ntarget = "out"\ninclude = ["personal/*"]\n'
            )
            xdg = root / "config"
            link = xdg / "skillink/skills.toml"
            link.parent.mkdir(parents=True)
            link.symlink_to(manifest)
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg)}, clear=True):
                self.assertEqual(config.manifest_path(), manifest)
                target, desired, _ = installer.selection(config.manifest_path(), "test")
                self.assertEqual(desired["hello"], str(skill))
                self.assertEqual(target, manifest.parent / "out")
                override = root / "override.toml"
                override.write_text("")
                os.environ["SKILLINK_MANIFEST"] = str(override)
                self.assertEqual(config.manifest_path(), override)
                self.assertEqual(config.manifest_path(link), manifest)
                os.environ["SKILLINK_MANIFEST"] = str(root / "missing.toml")
                with self.assertRaisesRegex(ValueError, "manifest not found"):
                    config.manifest_path()

    def test_default_home_and_missing_config_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            with patch.dict(os.environ, {"HOME": str(home)}, clear=True):
                with self.assertRaisesRegex(ValueError, "set SKILLINK_MANIFEST"):
                    config.manifest_path()
                manifest = home / ".config/skillink/skills.toml"
                manifest.parent.mkdir(parents=True)
                manifest.write_text("")
                self.assertEqual(config.manifest_path(), manifest)


if __name__ == "__main__":
    unittest.main()
