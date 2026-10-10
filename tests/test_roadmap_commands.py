from __future__ import annotations
import json, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from hikari.commands.completion import render
from hikari.commands.init import create_project
from hikari.commands.notes import add, clear, list_notes
from hikari.commands.time import start, stop, status, report, format_duration
from hikari.commands.repos import add as add_repo, load as load_repos, remove as remove_repo

class RoadmapCommandTests(unittest.TestCase):
    def test_completion_shells_contain_commands(self):
        for shell in ("bash", "zsh", "fish"):
            text = render(shell)
            self.assertIn("doctor", text); self.assertIn("completion", text)

    def test_init_scaffolds_and_refuses_existing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo-app"
            create_project(target, "python-cli")
            self.assertTrue((target / "src/demo_app/__main__.py").is_file())
            with self.assertRaises(FileExistsError): create_project(target, "empty")

    def test_notes_crud(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"; project.mkdir(); home = Path(tmp) / "home"
            add(project, "TODO: tests", home)
            self.assertIn("TODO: tests", list_notes(project, home))
            self.assertTrue(clear(project, home)); self.assertEqual(list_notes(project, home), "No notes yet.")

    def test_time_start_stop_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"; project.mkdir(); home = Path(tmp) / "home"
            begin = datetime(2026, 1, 1, 10, 0, 0); end = begin + timedelta(minutes=65)
            start(project, home, begin); self.assertEqual(status(project, home, end)["duration_seconds"], 3900)
            self.assertEqual(stop(project, home, end), 3900)
            self.assertEqual(report(project, home)["sessions"], 1)
            self.assertEqual(format_duration(3900), "1h 5m")

    def test_repo_registry_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "repo"; project.mkdir(); home = root / "home"
            self.assertTrue(add_repo(project, home)); self.assertFalse(add_repo(project, home))
            self.assertEqual(len(load_repos(home)["repos"]), 1)
            self.assertTrue(remove_repo(project, home)); self.assertEqual(load_repos(home)["repos"], [])

if __name__ == "__main__": unittest.main()
