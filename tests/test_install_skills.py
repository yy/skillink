"""Exercise installation against disposable sources and homes."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "install_skills", Path(__file__).resolve().parents[1] / "bin/install_skills.py"
)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = self.root / "skills.toml"
        self.target = self.root / "installed"
        self.source = self.root / "source"
        self.skill("alpha")
        self.write_manifest()

    def skill(self, name, source="source"):
        root = self.root / source / name
        root.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test {name}\n---\nRun the task.\n"
        )
        return root

    def write_manifest(self, include='["main/*"]', extra="", sources=""):
        self.manifest.write_text(
            'format_version = 1\n[sources]\nmain = "source"\n'
            + sources
            + '\n[profiles.test]\ntarget = "installed"\ninclude = '
            + include
            + "\n"
            + extra
        )

    def run_install(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return installer.install(self.manifest, "test", **kwargs)

    def test_dry_run_and_idempotence(self):
        self.run_install(dry_run=True)
        self.assertFalse(self.target.exists())
        self.run_install()
        self.assertEqual((self.target / "alpha").resolve(), self.source / "alpha")
        state = self.target / installer.STATE
        stamp = state.stat().st_mtime_ns
        self.assertEqual(self.run_install(check=True), 0)
        self.run_install()
        self.assertEqual(stamp, state.stat().st_mtime_ns)

    def test_prune_only_owned_links(self):
        self.run_install()
        (self.target / "unrelated").mkdir()
        (self.target / "foreign").symlink_to(self.root / "missing")
        self.write_manifest(include="[]")
        self.run_install()
        self.assertFalse((self.target / "alpha").is_symlink())
        self.assertTrue((self.source / "alpha/SKILL.md").is_file())
        self.assertTrue((self.target / "unrelated").is_dir())
        self.assertTrue((self.target / "foreign").is_symlink())

    def test_conflict_preflight_preserves_entire_install(self):
        self.run_install()
        state = (self.target / installer.STATE).read_bytes()
        self.skill("beta")
        self.skill("zeta")
        conflict = self.target / "zeta"
        conflict.mkdir()
        (conflict / "notes.txt").write_text("user work")
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertFalse((self.target / "beta").exists())
        self.assertEqual(state, (self.target / installer.STATE).read_bytes())
        self.assertEqual((conflict / "notes.txt").read_text(), "user work")

    def test_modified_managed_link_is_preserved(self):
        self.run_install()
        link = self.target / "alpha"
        link.unlink()
        link.symlink_to(self.root / "other")
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(link.readlink(), self.root / "other")

    def test_variant_resources_and_switch_back(self):
        root = self.source / "alpha"
        (root / "references").mkdir()
        (root / "references/example.txt").write_text("shared example")
        (root / "variants").mkdir()
        detailed = root / "variants/detailed.md"
        detailed.write_text((root / "SKILL.md").read_text() + "Extra steps.\n")
        self.run_install()
        self.write_manifest(extra='[profiles.test.variants]\n"main/alpha" = "detailed"\n')
        self.run_install()
        installed = self.target / "alpha"
        self.assertFalse(installed.is_symlink())
        self.assertEqual((installed / "SKILL.md").resolve(), detailed)
        self.assertEqual(
            (installed / "references/example.txt").read_text(), "shared example"
        )
        self.assertEqual(self.run_install(check=True), 0)
        # Added source assets appear after another reconciliation.
        (root / "new.txt").write_text("new resource")
        self.run_install()
        self.assertEqual((installed / "new.txt").read_text(), "new resource")
        (installed / "user-notes").write_text("keep")
        self.write_manifest()
        with self.assertRaises(installer.InstallError):
            self.run_install()
        (installed / "user-notes").unlink()
        self.run_install()
        self.assertTrue(installed.is_symlink())
        self.assertTrue(detailed.exists())

    def test_directory_link_migration_never_edits_source(self):
        self.target.symlink_to(self.source, target_is_directory=True)
        self.skill("beta", "other")
        self.write_manifest(include='["main/*", "extra/*"]', sources='extra = "other"\n')
        before = sorted(str(p) for p in self.source.rglob("*"))
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.run_install(migrate=True, dry_run=True)
        self.assertTrue(self.target.is_symlink())
        self.run_install(migrate=True)
        self.assertFalse(self.target.is_symlink())
        self.assertTrue((self.target / "beta").is_symlink())
        self.assertEqual(before, sorted(str(p) for p in self.source.rglob("*")))
        self.assertEqual(self.run_install(check=True), 0)

    def test_stale_legacy_links(self):
        self.target.mkdir()
        (self.target / "alpha").symlink_to(self.source / "alpha")
        (self.target / "removed").symlink_to(self.source / "removed")
        self.run_install()
        self.assertTrue((self.target / "removed").is_symlink())
        self.run_install(migrate=True)
        self.assertEqual((self.target / "alpha").resolve(), self.source / "alpha")
        self.assertFalse((self.target / "removed").is_symlink())

    def test_collisions_exclusions_and_missing_sources(self):
        self.skill("alpha", "other")
        sources = 'extra = "other"\nunused = "absent"\n'
        self.write_manifest(include='["main/*", "extra/*"]', sources=sources)
        with self.assertRaisesRegex(installer.InstallError, "collision"):
            self.run_install()
        self.assertFalse(self.target.exists())
        self.write_manifest(
            include='["main/*", "extra/*"]',
            sources=sources,
            extra='exclude = ["extra/alpha"]\n',
        )
        self.run_install()
        self.assertEqual(self.run_install(check=True), 0)
        self.write_manifest(include='["unused/*"]', sources=sources)
        with self.assertRaisesRegex(installer.InstallError, "missing source"):
            self.run_install()

    def test_invalid_config_never_changes_links(self):
        cases = [
            ('["main/missing"]', ""),
            ('["main/../alpha"]', ""),
            ('["main/*"]', 'exclude = ["main/missing"]\n'),
            ('["main/*"]', "typo = true\n"),
            ('["main/*"]', '[profiles.test.variants]\n"main/alpha" = "missing"\n'),
            ('["main/*"]', '[profiles.test.variants]\n"main/alpha" = "../escape"\n'),
        ]
        for include, extra in cases:
            with self.subTest(include=include, extra=extra):
                self.write_manifest(include=include, extra=extra)
                with self.assertRaises(installer.InstallError):
                    self.run_install()
                self.assertFalse(self.target.exists())

    def test_target_override_and_cwd_independence(self):
        with contextlib.chdir(self.root.parent):
            self.run_install(target=str(self.root / "alternate"))
        self.assertFalse(self.target.exists())
        self.assertTrue((self.root / "alternate/alpha").is_symlink())

    def test_safe_install_preserves_existing_entries_and_stale_links(self):
        self.run_install()
        old = (self.target / "alpha").readlink()
        self.skill("beta")
        self.skill("zeta")
        (self.target / "zeta").mkdir()
        (self.target / "zeta/notes").write_text("keep")
        self.write_manifest(include='["main/beta", "main/zeta"]')
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install_safe(self.manifest, "test")
        self.assertEqual((self.target / "alpha").readlink(), old)
        self.assertEqual((self.target / "zeta/notes").read_text(), "keep")
        self.assertTrue((self.target / "beta").is_symlink())
        state = json.loads((self.target / installer.STATE).read_text())
        self.assertEqual(set(state["skills"]), {"alpha", "beta"})

    def test_state_cannot_claim_parent_paths(self):
        self.run_install()
        state = self.target / installer.STATE
        data = json.loads(state.read_text())
        data["skills"]["../source"] = str(self.source)
        state.write_text(json.dumps(data))
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertTrue((self.source / "alpha/SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
