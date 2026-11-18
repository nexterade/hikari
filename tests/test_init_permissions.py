"""Regression tests: `git init` on a non-writable target must fail with actionable help."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hikari.git import GitError, LocalProject, local_troubleshoot_text, permission_help, write_access_report  # noqa: E402

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


class InitPermissionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "proj"
        self.root.mkdir()

    def _lock(self):
        self.root.chmod(stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(lambda: self.root.chmod(0o755))

    @unittest.skipIf(IS_ROOT, "root bypasses permission bits")
    def test_readonly_folder_gives_actionable_error(self):
        self._lock()
        with self.assertRaises(GitError) as ctx:
            LocalProject(self.root).init_repo()
        msg = str(ctx.exception)
        self.assertIn("chmod -R u+rwX", msg)
        self.assertIn("ls -ld", msg)
        self.assertFalse((self.root / ".git").exists())

    def test_permission_denied_from_git_is_translated(self):
        class Proc:
            returncode = 1
            stdout = ""
            stderr = f"{'/x/.git'}: Permission denied"
        with patch("hikari.git.subprocess.run", return_value=Proc()):
            with self.assertRaises(GitError) as ctx:
                LocalProject(self.root).init_repo()
        self.assertIn("Permission denied", str(ctx.exception))
        self.assertIn("chmod -R u+rwX", str(ctx.exception))

    def test_missing_git_binary_is_explained(self):
        with patch("hikari.git.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(GitError) as ctx:
                LocalProject(self.root).init_repo()
        self.assertIn("pkg install git", str(ctx.exception))

    def test_dot_git_file_is_rejected_clearly(self):
        (self.root / ".git").write_text("junk", encoding="utf-8")
        with self.assertRaises(GitError) as ctx:
            LocalProject(self.root).init_repo()
        self.assertIn("not a directory", str(ctx.exception))

    def test_normal_folder_still_initializes(self):
        LocalProject(self.root).init_repo()
        self.assertTrue((self.root / ".git").is_dir())

    def test_report_and_text_are_read_only(self):
        before = sorted(p.name for p in self.root.iterdir())
        rows = write_access_report(self.root)
        text = local_troubleshoot_text(self.root)
        self.assertTrue(any(label == "Writable" for _ok, label, _d in rows))
        self.assertIn("read-only", text)
        self.assertEqual(before, sorted(p.name for p in self.root.iterdir()))

    @unittest.skipIf(IS_ROOT, "root bypasses permission bits")
    def test_troubleshoot_flags_unwritable_folder(self):
        self._lock()
        self.assertIn("NO", local_troubleshoot_text(self.root))

    def test_termux_hint_only_on_termux(self):
        with patch.dict(os.environ, {"TERMUX_VERSION": "0.118"}):
            self.assertIn("Termux tips", permission_help(self.root))
        with patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("Termux tips", permission_help(self.root))


if __name__ == "__main__":
    unittest.main()
