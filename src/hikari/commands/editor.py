from __future__ import annotations
import os
import shlex
import subprocess
from pathlib import Path

def open_in_editor(path: str | Path) -> int:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "vi")
    try:
        command = shlex.split(editor, posix=(os.name != "nt")) + [str(path)]
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError as exc:
        raise RuntimeError(f"Editor tidak ditemukan: {editor}. Set $VISUAL atau $EDITOR.") from exc
