"""Private per-project Markdown notes."""
from __future__ import annotations
import hashlib, os, subprocess
from datetime import datetime
from pathlib import Path

def notes_path(project: str | Path, home: str | Path | None = None) -> Path:
    root = Path(project).expanduser().resolve(); base = Path(home) if home else Path(os.environ.get("HIKARI_HOME", Path.home() / ".hikari"))
    key = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return base / "notes" / f"{root.name}-{key}.md"
def add(project: str | Path, text: str, home=None) -> Path:
    path = notes_path(project, home); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f: f.write(f"- [{datetime.now().strftime('%Y-%m-%d %H:%M')}] {text.strip()}\n")
    return path
def list_notes(project: str | Path, home=None) -> str:
    path = notes_path(project, home); return path.read_text(encoding="utf-8") if path.exists() else "No notes yet."
def edit(project: str | Path, home=None) -> None:
    path = notes_path(project, home); path.parent.mkdir(parents=True, exist_ok=True); path.touch(exist_ok=True)
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or ("notepad" if os.name == "nt" else "vi")
    subprocess.run([editor, str(path)], check=False)
def clear(project: str | Path, home=None) -> bool:
    path = notes_path(project, home)
    if path.exists(): path.unlink(); return True
    return False
