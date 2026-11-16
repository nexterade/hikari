"""Thin wrapper around GitHub CLI with authentication pre-checks."""
from __future__ import annotations
import shutil, subprocess
from pathlib import Path

def gh(args: list[str], path: str | Path = ".", confirm: bool = False) -> str:
    if not shutil.which("gh"): raise RuntimeError("gh CLI not found; install GitHub CLI")
    auth = subprocess.run(["gh", "auth", "status"], cwd=Path(path), capture_output=True, text=True)
    if auth.returncode: raise RuntimeError("GitHub CLI is not authenticated; run gh auth login")
    if confirm and input("This action may change GitHub state. Continue? [y/N] ").strip().lower() not in {"y", "yes"}: return "Cancelled."
    p = subprocess.run(["gh", *args], cwd=Path(path), capture_output=True, text=True, check=False)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "gh command failed")
    return p.stdout.strip()
