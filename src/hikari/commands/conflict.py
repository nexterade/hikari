"""Interactive helper for resolving Git merge conflicts."""
from __future__ import annotations
import subprocess
from pathlib import Path

def conflicted_files(path: str | Path = ".") -> list[str]:
    p = subprocess.run(["git", "-C", str(Path(path).resolve()), "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True, check=False)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "Unable to inspect conflicts")
    return [x for x in p.stdout.splitlines() if x]
def apply_choice(path: str | Path, file: str, choice: str) -> bool:
    root = Path(path).resolve(); target = (root / file).resolve()
    if root not in target.parents and target != root: raise ValueError("Conflict path escapes repository")
    if choice in {"1", "2"}: args = ["git", "-C", str(root), "checkout", "--ours" if choice == "1" else "--theirs", "--", file]
    elif choice == "3":
        from .editor import open_in_editor
        return open_in_editor(target) == 0 == 0
    elif choice == "4": args = ["git", "-C", str(root), "add", "--", file]
    elif choice == "0": return False
    else: raise ValueError("choice must be 0, 1, 2, 3, or 4")
    return subprocess.run(args, capture_output=True, text=True, check=False).returncode == 0
