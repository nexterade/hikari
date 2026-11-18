"""Registry for multiple local project directories."""
from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path

def registry_path(home=None): return (Path(home) if home else Path(os.environ.get("HIKARI_HOME", Path.home() / ".hikari"))) / "repos.json"
def load(home=None):
    try: d = json.loads(registry_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError): d = {"repos": []}
    if not isinstance(d, dict) or not isinstance(d.get("repos"), list): return {"repos": []}
    return d
def _save(d, home=None):
    p = registry_path(home); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
def add(path, home=None):
    p = Path(path).expanduser().resolve()
    if not p.is_dir(): raise ValueError(f"Not a directory: {p}")
    d = load(home)
    if any(x.get("path") == str(p) for x in d["repos"]): return False
    d["repos"].append({"path": str(p), "added": datetime.now().isoformat(timespec="seconds")}); _save(d, home); return True
def remove(path, home=None):
    p = str(Path(path).expanduser().resolve()); d = load(home); old = len(d["repos"])
    d["repos"] = [x for x in d["repos"] if x.get("path") != p]; _save(d, home); return len(d["repos"]) < old
