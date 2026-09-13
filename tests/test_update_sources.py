"""Exercise source updates using local Git remotes, without network access."""

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "update_sources", Path(__file__).resolve().parents[1] / "bin/update_sources.py"
)
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.remote = self.root / "remote.git"
        self.git(self.root, "init", "--bare", str(self.remote))
        self.author = self.root / "author"
        self.git(self.root, "clone", str(self.remote), str(self.author))
        self.commit(self.author, "initial")
        self.git(self.author, "push", "-u", "origin", "HEAD")
        self.checkout = self.root / "checkout"
        self.git(self.root, "clone", str(self.remote), str(self.checkout))
        self.manifest = self.root / "skills.toml"
        self.manifest.write_text(
            'format_version = 1\n[sources]\none = "checkout"\ntwo = "checkout"\n'
        )

    def commit(self, root, content):
        (root / "tracked.txt").write_text(content)
        self.git(root, "add", "tracked.txt")
        self.git(
            root,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            content,
        )

    def update(self, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = updater.update(self.manifest, **kwargs)
        return result, output.getvalue()

    def test_dry_run_and_deduplicated_fast_forward(self):
        self.commit(self.author, "upstream")
        self.git(self.author, "push")
        before = self.git(self.checkout, "rev-parse", "HEAD")
        result, output = self.update(dry_run=True)
        self.assertEqual(result, 0)
        self.assertEqual(output.count("WOULD UPDATE"), 1)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), before)
        self.assertFalse((self.checkout / ".git/FETCH_HEAD").exists())
        result, output = self.update()
        self.assertEqual(result, 0)
        self.assertEqual(output.count("UPDATED"), 1)
        self.assertEqual((self.checkout / "tracked.txt").read_text(), "upstream")

    def test_dirty_and_diverged_repositories_preserve_work(self):
        (self.checkout / "tracked.txt").write_text("local work")
        result, output = self.update()
        self.assertEqual(result, 1)
        self.assertIn("local changes", output)
        self.assertEqual((self.checkout / "tracked.txt").read_text(), "local work")
        self.commit(self.checkout, "local commit")
        before = self.git(self.checkout, "rev-parse", "HEAD")
        self.commit(self.author, "upstream commit")
        self.git(self.author, "push")
        result, output = self.update()
        self.assertEqual(result, 1)
        self.assertIn("FAILED", output)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), before)
        self.assertEqual((self.checkout / "tracked.txt").read_text(), "local commit")

    def test_missing_source_does_not_block_other_sources(self):
        with self.manifest.open("a") as stream:
            stream.write('missing = "missing"\n')
        result, output = self.update()
        self.assertEqual(result, 1)
        self.assertIn("SKIP missing", output)
        self.assertIn("UPDATED one, two", output)


if __name__ == "__main__":
    unittest.main()
