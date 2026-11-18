from __future__ import annotations
import os, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "NO_COLOR": "1"}
class CliRoadmapTests(unittest.TestCase):
    def run_cli(self, *args): return subprocess.run([sys.executable, "-m", "hikari", *map(str,args)], cwd=ROOT, env=ENV, text=True, capture_output=True)
    def test_version_flag(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0); self.assertRegex(result.stdout, r"^hikari \S+ \(python \d+\.\d+\.\d+\)\n$")
    def test_status_json_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(tmp, "status", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            import json
            data = json.loads(result.stdout)
            self.assertIn("changes", data); self.assertIn("last_commit", data); self.assertIn("timestamp", data)
    def test_completion_command(self):
        result = self.run_cli("completion", "fish")
        self.assertEqual(result.returncode, 0); self.assertIn("complete -c hikari", result.stdout)
if __name__ == "__main__": unittest.main()
