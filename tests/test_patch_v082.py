from __future__ import annotations
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)


def init_repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "a@b")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "latest.json").write_text("initial\n", encoding="utf-8")
    git(tmp_path, "add", "-A"); git(tmp_path, "commit", "-qm", "initial")


def test_b1_profile_works_when_tomllib_missing(tmp_path):
    script = "import sys; sys.modules['tomllib'] = None; from hikari.profile import generate_repository_profile; print(generate_repository_profile(sys.argv[1])['name'])"
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "1.2.3"\n', encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == tmp_path.name


def test_b2_preserves_first_status_path_and_auto_commit_prefix(tmp_path):
    from hikari.git import GitRepo, auto_commit_message
    init_repo(tmp_path)
    (tmp_path / "latest.json").write_text("changed\n", encoding="utf-8")
    repo = GitRepo(tmp_path)
    assert " M latest.json" in repo.status_porcelain()
    assert auto_commit_message(repo).startswith("chore:")


def test_b2b_counts_unmerged_as_modified():
    from hikari.git import count_changes, parse_porcelain
    assert count_changes(parse_porcelain("UU conflict.txt\0"))["modified"] == 1


def test_b3_filename_substrings_do_not_trigger_test_or_fix(tmp_path):
    from hikari.git import auto_commit_message
    (tmp_path / "latest.json").write_text("x", encoding="utf-8")
    class Repo:
        root = tmp_path
        def run(self, *args, **kwargs): return " M latest.json\0"
    assert auto_commit_message(Repo()).startswith("chore:")


def test_b4_release_notes_have_version_heading_and_round_trip(tmp_path):
    init_repo(tmp_path)
    git(tmp_path, "tag", "v0.8.1")
    (tmp_path / "x.py").write_text("x\n", encoding="utf-8")
    git(tmp_path, "add", "x.py"); git(tmp_path, "commit", "-qm", "fix: repair thing")
    from hikari.commands.release_notes import generate
    notes = generate(tmp_path, version="v0.8.2")
    assert notes.startswith("## v0.8.2 - ")
    assert "### Fixed" in notes
    changelog = tmp_path / "docs" / "CHANGELOG.md"; changelog.parent.mkdir()
    changelog.write_text("# Changelog\n\n## v0.8.1\n\n- Old\n", encoding="utf-8")
    existing = changelog.read_text()
    updated = existing.replace("\n## v0.8.1", "\n" + notes + "\n\n## v0.8.1")
    changelog.write_text(updated, encoding="utf-8")
    from hikari.release import build_changelog_notes
    assert "repair thing" in build_changelog_notes(tmp_path, "v0.8.2")


def test_b4_cli_write_inserts_versioned_entry_and_refuses_duplicate(tmp_path, monkeypatch):
    init_repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.8.2"\n', encoding="utf-8")
    git(tmp_path, "add", "pyproject.toml"); git(tmp_path, "commit", "-qm", "fix: repair thing")
    changelog = tmp_path / "docs" / "CHANGELOG.md"; changelog.parent.mkdir(); changelog.write_text("# Changelog\n\n## 0.8.1\n\n- Old\n", encoding="utf-8")
    from hikari import cli
    cli.main(["--path", str(tmp_path), "release", "notes", "--from", "HEAD~1", "--write"])
    text = changelog.read_text(encoding="utf-8")
    assert text.index("## v0.8.2") < text.index("## 0.8.1")
    with __import__("pytest").raises(SystemExit):
        cli.main(["--path", str(tmp_path), "release", "notes", "--from", "HEAD~1", "--write"])
    assert text == changelog.read_text(encoding="utf-8")


def test_b5_notes_show_does_not_open_editor(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HIKARI_HOME", str(home))
    from hikari.commands.notes import add
    add(tmp_path, "hello")
    from hikari import cli
    with patch("hikari.commands.editor.open_in_editor", side_effect=AssertionError("editor opened")):
        cli.main(["--path", str(tmp_path), "notes", "show"])
    assert "hello" in capsys.readouterr().out


def test_b6_editor_supports_arguments_and_visual_precedence(tmp_path, monkeypatch):
    from hikari.commands.editor import open_in_editor
    monkeypatch.setenv("VISUAL", f"{sys.executable} -c \"import sys; open(sys.argv[1], 'w').write('ok')\"")
    monkeypatch.setenv("EDITOR", "missing-editor")
    assert open_in_editor(tmp_path / "note.md") == 0
    assert (tmp_path / "note.md").read_text() == "ok"


def test_b7_status_json_does_not_use_hikari_version_for_target(tmp_path, capsys):
    from hikari import cli
    cli.main(["--path", str(tmp_path), "status", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["version"] is None
    assert data["version_source"] is None
    assert data["hikari_version"]


def test_b8_github_commands_validate_number_and_use_pr_base(tmp_path, monkeypatch):
    from hikari import cli
    calls = []
    monkeypatch.setattr("hikari.commands.github.gh", lambda args, path, confirm=False: calls.append((args, confirm)) or "ok")
    with patch("hikari.cli.GitRepo", side_effect=Exception("stop")):
        pass
    # main requires a Git repo for these commands; use a real one.
    init_repo(tmp_path)
    cli.main(["--path", str(tmp_path), "pr", "create", "--title", "T", "--body", "B", "--base", "develop"])
    assert calls[-1][0] == ["pr", "create", "--title", "T", "--base", "develop", "--body", "B"]
    with __import__("pytest").raises(SystemExit):
        cli.main(["--path", str(tmp_path), "pr", "view"])


def test_b9_changelog_names_are_exact_and_scan_prunes(tmp_path):
    from hikari.git import find_changelogs
    (tmp_path / "exchanges.md").write_text("x", encoding="utf-8")
    (tmp_path / "newsletter.md").write_text("x", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("x", encoding="utf-8")
    huge = tmp_path / "node_modules" / "huge"; huge.mkdir(parents=True)
    (huge / "CHANGES.md").write_text("x", encoding="utf-8")
    names = [p.name for p in find_changelogs(tmp_path)]
    assert names == ["CHANGELOG.md"]


def test_b10_cli_has_no_literal_backslash_n_in_fixed_output_lines():
    text = (ROOT / "src/hikari/cli.py").read_text(encoding="utf-8")
    assert 'marker + "\\\\nNo action history yet."' not in text
    assert 'print("\\\\n" + history)' not in text
    assert 'print("\\\\n  [1] Refresh details")' not in text
    assert 'input(color("\\\\n  ❯ ", MAGENTA))' not in text
