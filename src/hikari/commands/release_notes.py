"""Generate release notes from Conventional Commit subjects."""
from __future__ import annotations
import re, subprocess
from pathlib import Path
GROUPS = {"feat": "Added", "fix": "Fixed", "docs": "Changed", "refactor": "Changed", "chore": "Changed", "perf": "Changed", "remove": "Removed"}
def generate(path: str | Path = ".", from_ref: str | None = None, to_ref: str = "HEAD", template: str = "keepachangelog") -> str:
    if template not in {"keepachangelog", "simple", "github"}: raise ValueError("unknown release notes template")
    if from_ref: rev = f"{from_ref}..{to_ref}"
    else:
        p = subprocess.run(["git", "-C", str(Path(path).resolve()), "describe", "--tags", "--abbrev=0"], capture_output=True, text=True)
        if p.returncode: raise RuntimeError("No previous tag found; pass --from explicitly")
        rev = f"{p.stdout.strip()}..{to_ref}"
    p = subprocess.run(["git", "-C", str(Path(path).resolve()), "log", rev, "--pretty=format:%s"], capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "git log failed")
    if template == "simple": return "\n".join(f"- {s}" for s in p.stdout.splitlines()) or "No commits in range."
    groups = {}
    for subject in p.stdout.splitlines():
        m = re.match(r"([a-z]+)(?:\([^)]*\))?!?:\s*(.+)", subject, re.I)
        key = GROUPS.get(m.group(1).lower(), "Changed") if m else "Changed"; text = m.group(2) if m else subject
        groups.setdefault(key, []).append(text)
    order = ["Added", "Changed", "Fixed", "Removed"]
    return "\n\n".join("### " + k + "\n" + "\n".join("- " + v for v in groups[k]) for k in order if groups.get(k)) or "No commits in range."
