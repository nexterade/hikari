"""Git diff helpers."""
from __future__ import annotations
import os, shutil, subprocess
from pathlib import Path

def get_diff(path: str | Path = ".", file: str | None = None, staged: bool = False, stat: bool = False) -> str:
    if not shutil.which("git"): raise RuntimeError("Git not found; install Git first")
    args = ["git", "-C", str(Path(path).resolve()), "diff", "--color=never" if "NO_COLOR" in os.environ else "--color=always"]
    if staged: args.append("--staged")
    if stat: args.append("--stat")
    if file: args.extend(["--", file])
    p = subprocess.run(args, capture_output=True, text=True, check=False)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "git diff failed")
    return p.stdout
