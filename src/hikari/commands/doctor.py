"""Read-only environment diagnostics for HIKARI."""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path
from .. import palette

def _run(args: list[str]) -> tuple[bool, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
        out = (p.stdout or p.stderr).strip().splitlines()
        return p.returncode == 0, out[0] if out else ("available" if p.returncode == 0 else "failed")
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)

def check_environment(target: Path | str = ".") -> list[tuple[bool, str, str]]:
    target = Path(target).expanduser().resolve()
    py_ok = sys.version_info >= (3, 10)
    checks = [(py_ok, f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "" if py_ok else "Python >= 3.10 required")]
    for exe, args in [("git", ["git", "--version"]), ("gh", ["gh", "--version"])]:
        if shutil.which(exe):
            ok, val = _run(args); checks.append((ok, val, "" if ok else f"{exe} command failed"))
        else: checks.append((False, "not found", f"Install {exe}"))
    if shutil.which("gh"):
        ok, _ = _run(["gh", "auth", "status"]); checks.append((ok, "logged in" if ok else "not logged in", "" if ok else "Run gh auth login"))
    else: checks.append((False, "unavailable", "Install gh CLI first"))
    writable = target.is_dir() and os.access(target, os.W_OK)
    checks.append((writable, str(target), "target must exist and be writable" if not writable else ""))
    home = Path(os.environ.get("HIKARI_HOME", Path.home() / ".hikari")); backups = home / "backups"
    try: backups.mkdir(parents=True, exist_ok=True); backup_ok, backup_note = True, ""
    except OSError: backup_ok, backup_note = False, "cannot create backup folder"
    checks.append((backup_ok, str(backups), backup_note))
    config = home / "config.toml"; checks.append((True, str(config), "default (not created)" if not config.exists() else ""))
    return checks

def run(target: Path | str = ".") -> int:
    labels = ["Python", "Git", "gh CLI", "gh auth", "Target folder", "Backup folder", "Config file"]
    checks = check_environment(target)
    print("─" * 64 + "\n  # HIKARI DOCTOR\n" + "─" * 64)
    for label, (ok, value, note) in zip(labels, checks):
        mark = "✓" if ok else "✗"; suffix = f"  ({note})" if note else ""
        print(f"  {palette.VARIABLE}{label:<18}{palette.RESET}:  {palette.GRAY_VALUE}{value}{palette.RESET} {mark}{suffix}")
    print("─" * 64)
    failures = sum(not c[0] for c in checks)
    print("  NEXT: Semua prasyarat siap." if not failures else f"  NEXT: Perbaiki {failures} pemeriksaan di atas.")
    return 0 if not failures else 1
