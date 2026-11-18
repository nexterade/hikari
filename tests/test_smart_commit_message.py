"""Behavioural tests for the smart commit-message engine (real temporary Git repos)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hikari.commit_message import CommitSuggestion, classify, detect_style, suggest_commit_message  # noqa: E402
from hikari.git import GitRepo, auto_commit_message  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.x",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.x"}


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, env=ENV)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, msg="init"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", msg)

    def suggest(self) -> CommitSuggestion:
        return suggest_commit_message(GitRepo(self.root))


class ClassifyTests(unittest.TestCase):
    def test_categories(self):
        cases = {
            "src/app.py": "source", "tests/test_app.py": "test", "web/app.spec.ts": "test",
            "README.md": "docs", "docs/guide.html": "docs", ".github/workflows/test.yml": "ci",
            "pyproject.toml": "build", "requirements-dev.txt": "build", "Dockerfile": "build",
            "latest.json": "config", ".gitignore": "config", "logo.png": "asset",
        }
        for path, expected in cases.items():
            self.assertEqual(classify(path), expected, path)

    def test_filename_substrings_never_mean_tests(self):
        self.assertEqual(classify("latest.json"), "config")
        self.assertEqual(classify("src/contest.py"), "source")


class SuggestionTests(RepoCase):
    def test_new_source_file_is_feat(self):
        self.write("a.txt", "x")
        self.commit()
        self.write("src/engine.py", "def run():\n    pass\n")
        s = self.suggest()
        self.assertEqual(s.subject, "feat: add engine.py")

    def test_fix_wording_in_added_lines_is_fix_without_duplicate_verb(self):
        self.write("src/core.py", "def f():\n    return 1\n")
        self.commit()
        self.write("src/core.py", "def f():\n    # fix crash on empty input\n    return 2\n")
        self.assertEqual(self.suggest().type, "fix")

    def test_new_public_function_in_existing_file_is_named(self):
        self.write("src/core.py", "def f():\n    return 1\n")
        self.commit()
        self.write("src/core.py", "def f():\n    return 1\n\ndef shiny():\n    pass\n\ndef _hidden():\n    pass\n")
        s = self.suggest()
        self.assertEqual(s.subject, "feat: add shiny")

    def test_plain_modification_does_not_claim_intent(self):
        self.write("src/core.py", "x = 1\n")
        self.commit()
        self.write("src/core.py", "x = 2\n")
        self.assertEqual(self.suggest().subject, "chore: update core.py")

    def test_version_bump(self):
        self.write("VERSION", "0.1.0\n")
        self.write("CHANGELOG.md", "# Changelog\n")
        self.commit()
        self.write("VERSION", "0.2.0\n")
        self.write("CHANGELOG.md", "# Changelog\n\n## 0.2.0\n- Add thing\n")
        self.assertEqual(self.suggest().subject, "chore: bump version to v0.2.0")

    def test_changelog_entry_drives_subject_and_type(self):
        self.write("src/m.py", "x = 1\n")
        self.write("CHANGELOG.md", "# Changelog\n")
        self.commit()
        self.write("src/m.py", "x = 2\n")
        self.write("CHANGELOG.md", "# Changelog\n\n## Unreleased\n- Fixed startup failure when tomllib is missing\n")
        s = self.suggest()
        self.assertEqual(s.subject, "fix: startup failure when tomllib is missing")

    def test_dependency_manifest_is_build(self):
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.commit()
        self.write("pyproject.toml", "[project]\nname='x'\ndependencies=['requests']\n")
        self.assertEqual(self.suggest().subject, "build: update pyproject.toml")

    def test_ci_tests_docs_types(self):
        self.write("a", "1")
        self.commit()
        self.write(".github/workflows/t.yml", "name: t\n")
        self.assertEqual(self.suggest().type, "ci")
        git(self.root, "add", "-A"); git(self.root, "commit", "-qm", "ci")
        self.write("tests/test_a.py", "def test_a(): pass\n")
        self.assertEqual(self.suggest().type, "test")
        git(self.root, "add", "-A"); git(self.root, "commit", "-qm", "t")
        self.write("docs/guide.md", "# g\n")
        self.assertEqual(self.suggest().type, "docs")

    def test_rename_and_delete(self):
        self.write("src/old.py", "x = 1\n")
        self.write("src/keep.py", "y = 1\n")
        self.commit()
        git(self.root, "mv", "src/old.py", "src/new.py")
        self.assertEqual(self.suggest().subject, "refactor: rename old.py to new.py")
        git(self.root, "add", "-A"); git(self.root, "commit", "-qm", "mv")
        git(self.root, "rm", "-q", "src/new.py")
        self.assertEqual(self.suggest().subject, "chore: remove new.py")

    def test_many_files_get_body_and_short_subject(self):
        self.write("a", "1")
        self.commit()
        for i in range(6):
            self.write(f"src/pkg/m{i}.py", f"v{i} = 1\n")
        s = self.suggest()
        self.assertLessEqual(len(s.subject), 72)
        self.assertIn("6 files in src/pkg", s.subject)
        self.assertTrue(s.body.startswith("- add src/pkg/m0.py"))
        self.assertIn("\n\n", s.full)

    def test_first_commit_without_head_works(self):
        self.write("src/main.py", "def start():\n    pass\n")
        self.assertTrue(self.suggest().subject.startswith("feat:"))

    def test_secret_files_are_warned_and_never_read(self):
        self.write("a", "1")
        self.commit()
        self.write(".env", "TOKEN=fix-bug-crash\n")
        s = self.suggest()
        self.assertTrue(any(".env" in w for w in s.warnings))
        self.assertEqual(s.type, "chore")

    def test_backward_compatible_wrapper_returns_subject(self):
        self.write("a", "1")
        self.commit()
        self.write("a", "2")
        self.assertEqual(auto_commit_message(GitRepo(self.root)), self.suggest().subject)

    def test_subject_never_exceeds_72_chars(self):
        self.write("a", "1")
        self.commit()
        self.write("x" * 90 + ".py", "v = 1\n")
        self.assertLessEqual(len(self.suggest().subject), 72)


class HistoryStyleTests(RepoCase):
    def history(self, subjects):
        for i, msg in enumerate(subjects):
            self.write("f.txt", str(i))
            self.commit(msg)

    def test_plain_history_gives_plain_sentence(self):
        self.history(["Add readme", "Fix parser", "Update styles", "Improve docs", "Add tests", "Tweak config"])
        self.write("src/new.py", "x = 1\n")
        s = self.suggest()
        self.assertEqual(s.style, "plain")
        self.assertEqual(s.subject, "Add new.py")

    def test_scoped_history_adds_scope(self):
        self.history(["feat(api): a", "fix(ui): b", "docs(readme): c", "chore(ci): d", "feat(core): e"])
        self.write("src/new.py", "x = 1\n")
        self.assertEqual(self.suggest().subject, "feat(new): add new.py")

    def test_short_history_defaults_to_conventional_without_scope(self):
        self.history(["init", "second"])
        self.write("src/new.py", "x = 1\n")
        self.assertEqual(self.suggest().subject, "feat: add new.py")

    def test_detect_style_ignores_merges(self):
        subs = ["Merge branch x"] * 10
        self.assertEqual(detect_style(subs)[0], "conventional")


if __name__ == "__main__":
    unittest.main()
