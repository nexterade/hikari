"""Create new project scaffolds from built-in templates."""
from __future__ import annotations
import subprocess
from pathlib import Path
TEMPLATES = {
 "python-cli": {"dirs": ["src/{name}", "tests"], "files": {
  "pyproject.toml": '[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n\n[project.scripts]\n{name} = "{name}.__main__:main"\n',
  "README.md": "# {name}\n\nA Python CLI project.\n", ".gitignore": "__pycache__/\n*.py[cod]\n.venv/\n",
  "src/{name}/__init__.py": '"""{name} package."""\n',
  "src/{name}/__main__.py": 'def main():\n    print("Hello from {name}!")\n\nif __name__ == "__main__":\n    main()\n',
  "tests/__init__.py": "", "tests/test_main.py": "import unittest\n\nclass SmokeTest(unittest.TestCase):\n    def test_true(self): self.assertTrue(True)\n\nif __name__ == \"__main__\": unittest.main()\n"}},
 "python-lib": {"dirs": ["src/{name}", "tests"], "files": {
  "pyproject.toml": '[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
  "README.md": "# {name}\n\nA Python library.\n", ".gitignore": "__pycache__/\n*.py[cod]\n.venv/\n",
  "src/{name}/__init__.py": '"""{name} library."""\n', "tests/__init__.py": ""}},
 "empty": {"dirs": [], "files": {".gitkeep": ""}}
}
def create_project(target: str | Path, template: str = "python-cli", init_git: bool = False) -> Path:
    target = Path(target).expanduser().resolve(); name = target.name.replace("-", "_").replace(" ", "_")
    if template not in TEMPLATES: raise ValueError(f"Unknown template: {template}")
    if target.exists(): raise FileExistsError(f"Target already exists: {target}")
    spec = TEMPLATES[template]; target.mkdir(parents=True)
    for item in spec["dirs"]: (target / item.format(name=name)).mkdir(parents=True, exist_ok=True)
    for rel, content in spec["files"].items():
        path = target / rel.format(name=name); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content.format(name=name), encoding="utf-8")
    if init_git: subprocess.run(["git", "init", str(target)], check=True, capture_output=True, text=True)
    return target
