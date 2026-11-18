"""Local per-project time tracking."""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timedelta
from pathlib import Path

def data_path(project: str | Path, home=None) -> Path:
    root = Path(project).expanduser().resolve(); base = Path(home) if home else Path(os.environ.get("HIKARI_HOME", Path.home() / ".hikari"))
    return base / "time" / (hashlib.sha256(str(root).encode()).hexdigest()[:12] + ".json")
def _load(path):
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): data = {"sessions": [], "active": None}
    if not isinstance(data, dict): data = {"sessions": [], "active": None}
    data.setdefault("sessions", []); data.setdefault("active", None); return data
def _save(path, data): path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
def start(project, home=None, now=None):
    p = data_path(project, home); d = _load(p)
    if d["active"]: raise ValueError("A session is already active")
    d["active"] = (now or datetime.now()).isoformat(timespec="seconds"); _save(p, d); return d["active"]
def stop(project, home=None, now=None):
    p = data_path(project, home); d = _load(p)
    if not d["active"]: raise ValueError("No active session")
    begin = datetime.fromisoformat(d["active"]); end = now or datetime.now(); secs = max(0, int((end - begin).total_seconds()))
    d["sessions"].append({"start": d["active"], "end": end.isoformat(timespec="seconds"), "duration_seconds": secs}); d["active"] = None; _save(p, d); return secs
def status(project, home=None, now=None):
    d = _load(data_path(project, home)); total = sum(int(s.get("duration_seconds", 0)) for s in d["sessions"])
    if d["active"]: total += max(0, int(((now or datetime.now()) - datetime.fromisoformat(d["active"])).total_seconds()))
    return {"active": d["active"], "sessions": len(d["sessions"]), "duration_seconds": total}
def report(project, home=None, period="all", now=None):
    d = _load(data_path(project, home)); sessions = d["sessions"]
    if period in {"week", "month"}:
        cutoff = (now or datetime.now()) - timedelta(days=7 if period == "week" else 30)
        sessions = [s for s in sessions if datetime.fromisoformat(s["start"]) >= cutoff]
    return {"sessions": len(sessions), "duration_seconds": sum(int(s.get("duration_seconds", 0)) for s in sessions)}
def format_duration(seconds: int) -> str:
    h, rem = divmod(max(0, seconds), 3600); m = rem // 60
    return f"{h}h {m}m" if h else (f"{m}m" if m else "0m")
