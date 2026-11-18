from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .constants import SKIP_DIRS

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


class GitError(RuntimeError):
    pass


def iter_project_files(root: Path):
    """Yield non-symlink project files while pruning known heavy/metadata dirs."""
    import os
    root = Path(root)
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP_DIRS and not (Path(current) / d).is_symlink())
        for filename in sorted(filenames):
            path = Path(current) / filename
            if not path.is_symlink():
                yield path


def project_inventory(root: Path) -> dict[str, object]:
    """Collect safe, local-only inventory metadata for human-readable reports."""
    ignored = SKIP_DIRS
    files: list[Path] = []
    dirs = 0
    for current, dirnames, filenames in __import__("os").walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ignored and not (Path(current) / d).is_symlink())
        dirs += len(dirnames)
        folder = Path(current)
        files.extend(folder / name for name in filenames if name not in {".DS_Store"})
    total_bytes = 0
    file_count = 0
    latest: tuple[float, Path] | None = None
    extensions: dict[str, int] = {}
    for path in files:
        if path.is_symlink():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        file_count += 1
        total_bytes += stat.st_size
        if latest is None or stat.st_mtime > latest[0]:
            latest = (stat.st_mtime, path)
        ext = path.suffix.lower() or "[no extension]"
        extensions[ext] = extensions.get(ext, 0) + 1
    return {"files": file_count, "dirs": dirs, "bytes": total_bytes,
            "latest": latest, "extensions": extensions}


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def inventory_lines(root: Path) -> list[str]:
    info = project_inventory(root)
    lines = [f"  Location      {root}", f"  Scanned at    {datetime.now().astimezone().isoformat(timespec='seconds')}",
             f"  Directories   {info['dirs']}", f"  Files         {info['files']}", f"  Total size    {human_size(int(info['bytes']))}"]
    latest = info["latest"]
    if latest:
        stamp, path = latest
        lines.append(f"  Latest file   {path.relative_to(root)}")
        lines.append(f"  Modified at   {datetime.fromtimestamp(stamp).astimezone().isoformat(timespec='seconds')}")
    else:
        lines.append("  Latest file   (no files found)")
    return lines

def _is_termux() -> bool:
    import os
    return bool(os.environ.get("TERMUX_VERSION")) or "com.termux" in os.environ.get("PREFIX", "")


def write_access_report(root: Path) -> list[tuple[bool, str, str]]:
    """Read-only permission checks for a target folder: (ok, label, detail).

    Only inspects metadata (stat/os.access); never creates or changes anything.
    """
    import os
    import stat as _stat
    root = Path(root)
    rows: list[tuple[bool, str, str]] = []
    try:
        st = root.stat()
    except OSError as exc:
        return [(False, "Folder", f"cannot read folder metadata: {exc}")]
    uid = os.getuid() if hasattr(os, "getuid") else None
    mode = _stat.filemode(st.st_mode)
    owner_ok = uid is None or st.st_uid == uid
    rows.append((owner_ok, "Owner", f"folder uid={st.st_uid}, you uid={uid}" + ("" if owner_ok else "  (folder belongs to another user/app)")))
    rows.append((True, "Mode", mode))
    w_ok = os.access(root, os.W_OK)
    x_ok = os.access(root, os.X_OK)
    rows.append((w_ok, "Writable", "yes" if w_ok else "NO — HIKARI/Git cannot create files here"))
    rows.append((x_ok, "Enterable", "yes" if x_ok else "NO — folder lacks the execute (x) bit"))
    dot_git = root / ".git"
    if dot_git.is_symlink() or dot_git.exists():
        if dot_git.is_dir():
            g_ok = os.access(dot_git, os.W_OK | os.X_OK)
            rows.append((g_ok, ".git", "exists (directory)" + ("" if g_ok else " but is NOT writable")))
        else:
            rows.append((False, ".git", "exists but is a FILE/symlink, not a directory"))
    else:
        rows.append((True, ".git", "not present"))
    return rows


def permission_help(root: Path) -> str:
    """Actionable, copy-paste friendly fix instructions for a non-writable target."""
    root = Path(root)
    lines = [
        f"Cannot write inside: {root}",
        "The folder is not writable by the user running HIKARI, so Git cannot create .git there.",
        "Nothing was changed. Fix it, then try again:",
        f"  1. Inspect:   ls -ld \"{root}\"     (also: id -u)",
        f"  2. Own it:    chmod -R u+rwX \"{root}\"",
        "  3. If step 2 says 'Operation not permitted', the folder is owned by another",
        "     user/app (e.g. extracted by a file manager or with root). Make a clean copy:",
        f"       cp -r \"{root}\" \"{root}_new\" && mv \"{root}\" \"{root}_old\" && mv \"{root}_new\" \"{root}\"",
    ]
    if _is_termux():
        lines += [
            "  Termux tips:",
            "    - Keep projects inside $HOME (~/project). Do NOT use /sdcard or ~/storage/shared:",
            "      shared storage cannot hold a normal .git (no chmod/symlink support).",
            "    - Run: termux-setup-storage  only if you intentionally copy files to/from shared storage.",
            "    - Do not run Termux commands with 'su'/root; it creates root-owned files.",
        ]
    lines.append("  Verify with:  hikari doctor " + str(root) + "   or menu [11] TROUBLESHOOT")
    return "\n".join(lines)


def local_troubleshoot_text(root: Path) -> str:
    """Read-only diagnosis for projects that are not Git repositories yet."""
    import shutil
    rows = write_access_report(root)
    out = ["\nLOCAL PROJECT DIAGNOSIS (read-only)", "=" * 56, f"  Target        {root}"]
    git_path = shutil.which("git")
    out.append(f"  {'✓' if git_path else '✗'} git           {git_path or 'not found — install it (Termux: pkg install git)'}")
    for ok, label, detail in rows:
        out.append(f"  {'✓' if ok else '✗'} {label:<13} {detail}")
    if any(not ok for ok, label, _ in rows if label in {"Writable", "Enterable", ".git", "Folder"}) :
        out += ["", permission_help(root)]
    elif not git_path:
        out += ["", "Next: install Git, then use [7] REPOSITORY → [1] to initialize."]
    else:
        out += ["", "Next: everything looks fine. Use [7] REPOSITORY → [1] to initialize local Git."]
    out.append("\nSafety: diagnosis is read-only. Nothing was created, changed, or uploaded.")
    return "\n".join(out)


class LocalProject:
    """Project target that does not require Git.

    HIKARI can inspect and manage a plain folder first, then initialize Git
    later from the same console.
    """

    def __init__(self, path: Path):
        self.root = path.expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise GitError(f"project folder not found: {self.root}")

    @property
    def name(self) -> str:
        return self.root.name

    def local_version(self) -> tuple[str | None, str | None]:
        # Reuse the exact local metadata detection logic without touching Git.
        return detect_local_version(self.root)

    def branch(self) -> str:
        return "(local only)"

    def remote(self) -> str:
        return "(none)"

    def status_porcelain(self) -> str:
        return ""

    def status_text(self) -> str:
        info = project_inventory(self.root)
        version, source = self.local_version()
        out = ["\nPROJECT STATUS", "=" * 56, f"  Project       {self.name}",
               *inventory_lines(self.root), f"  Version       {version or '(not detected)'}" + (f" ({source})" if source else ""),
               "  Git state     not initialized", "  Mode          local-only"]
        return "\n".join(out)

    def scan_text(self) -> str:
        info = project_inventory(self.root)
        out = ["\nLOCAL FILE SCAN", "=" * 56, *inventory_lines(self.root), "", "FILE TYPES"]
        ext = info["extensions"]
        if ext:
            out.extend(f"  {k:<20} {v:>5} file(s)" for k, v in sorted(ext.items(), key=lambda item: (-item[1], item[0]))[:30])
        else:
            out.append("  (no files found)")
        largest = []
        for p in iter_project_files(self.root):
            try:
                largest.append((p.stat().st_size, p))
            except OSError:
                continue
        largest.sort(key=lambda item: item[0], reverse=True)
        out.extend(["", "Largest files", *[f"  {human_size(size):>10}  {p.relative_to(self.root)}" for size, p in largest[:10]]])
        return "\n".join(out)

    def init_repo(self) -> "GitRepo":
        import os
        if not os.access(self.root, os.W_OK | os.X_OK):
            raise GitError(permission_help(self.root))
        git_dir = self.root / ".git"
        if git_dir.is_symlink() or (git_dir.exists() and not git_dir.is_dir()):
            raise GitError(f"{git_dir} already exists but is not a directory. Rename or remove it, then retry.")
        try:
            proc = subprocess.run(["git", "init"], cwd=self.root, text=True, capture_output=True)
        except FileNotFoundError:
            raise GitError("git is not installed or not on PATH. Termux: pkg install git — then retry.") from None
        if proc.returncode:
            detail = proc.stderr.strip() or proc.stdout.strip() or "git init failed"
            if "permission denied" in detail.lower():
                raise GitError(f"{detail}\n\n{permission_help(self.root)}")
            if "dubious ownership" in detail.lower():
                raise GitError(f"{detail}\n\nFix: git config --global --add safe.directory \"{self.root}\"")
            raise GitError(detail)
        return GitRepo(self.root)


def recommended_gitignore(root: Path) -> str:
    """Build a project-aware .gitignore without touching an existing file."""
    parts = ["# Generated by HIKARI/.LAB for this project", ""]
    files = {p.name for p in root.iterdir() if p.is_file()}
    dirs = {p.name for p in root.iterdir() if p.is_dir()}

    if "pyproject.toml" in files or "requirements.txt" in files or "setup.py" in files or any(root.glob("*.py")):
        parts += ["# Python", "__pycache__/", "*.py[cod]", ".pytest_cache/", ".coverage", "htmlcov/", ".venv/", "venv/", "env/", "build/", "dist/", "*.egg-info/", ""]
    if "package.json" in files or "package-lock.json" in files or "yarn.lock" in files or "pnpm-lock.yaml" in files:
        parts += ["# Node.js", "node_modules/", "npm-debug.log*", "yarn-debug.log*", "yarn-error.log*", ".npm/", "dist/", "coverage/", ""]
    if "Cargo.toml" in files:
        parts += ["# Rust", "target/", ""]
    if "go.mod" in files:
        parts += ["# Go", "bin/", "vendor/", ""]
    if "build.gradle" in files or "build.gradle.kts" in files or "settings.gradle" in files or "settings.gradle.kts" in files or "gradlew" in files:
        parts += ["# Gradle / Android", ".gradle/", "build/", "local.properties", "captures/", "*.apk", "*.aab", ""]

    parts += ["# Environment / secrets", ".env", ".env.*", "!.env.example", "*.pem", "*.key", "", "# Editors", ".vscode/", ".idea/", "", "# OS", ".DS_Store", "Thumbs.db"]
    return "\n".join(parts).rstrip() + "\n"

def detect_local_version(root: Path) -> tuple[str | None, str | None]:
    structured: list[tuple[str, str]] = [
        ("pyproject.toml", "pyproject.toml"),
        ("package.json", "package.json"),
        ("VERSION", "VERSION"),
        ("version.txt", "version.txt"),
        ("PROJECT_STATE.json", "PROJECT_STATE.json"),
    ]
    for filename, source in structured:
        path = root / filename
        if not path.is_file():
            continue
        try:
            if filename == "pyproject.toml" and tomllib is not None:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                value = data.get("project", {}).get("version")
            elif filename == "package.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                value = data.get("version")
            elif filename == "PROJECT_STATE.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                value = data.get("version") or data.get("project", {}).get("version")
            else:
                value = path.read_text(encoding="utf-8").strip()
            if value:
                match = re.search(r"\bv?(\d+\.\d+\.\d+)\b", str(value))
                if match:
                    return f"v{match.group(1)}", source
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
    for filename in ("CHANGELOG.md", "README.md", "README.rst", "README.txt", "PROJECT_STATE.json", "PROJECT_CONTINUATION.md"):
        path = root / filename
        if not path.is_file():
            continue
        try:
            match = re.search(r"(?<!\d)v?(\d+\.\d+\.\d+)", path.read_text(encoding="utf-8"), re.I)
            if match:
                return f"v{match.group(1)}", filename
        except (OSError, UnicodeError):
            continue
    return None, None


def parse_porcelain(raw: str) -> list[tuple[str, str, str | None]]:
    """Parse Git porcelain v1 -z output into (XY, path, original_path)."""
    entries: list[tuple[str, str, str | None]] = []
    fields = raw.split("\0")
    i = 0
    while i < len(fields):
        field = fields[i]
        i += 1
        if not field:
            continue
        if len(field) < 3:
            continue
        code, path = field[:2], field[3:]
        original = None
        if code[0] in "RC" or code[1] in "RC":
            if i < len(fields) and fields[i]:
                original = fields[i]
                i += 1
        entries.append((code, path, original))
    return entries


def count_changes(entries: list[tuple[str, str, str | None]]) -> dict[str, int]:
    counts = {"modified": 0, "added": 0, "deleted": 0, "untracked": 0}
    for code, _path, _original in entries:
        if code == "??":
            counts["untracked"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        elif "A" in code or "?" in code:
            counts["added"] += 1
        else:
            counts["modified"] += 1
    return counts


class GitRepo:
    def __init__(self, path: Path):
        self.root = path.expanduser().resolve()
        if not (self.root / ".git").exists():
            raise GitError(f"not a Git repository: {self.root}")
        # The .git marker is sufficient for construction; subprocess validation is lazy.

    @property
    def name(self) -> str:
        return self.root.name

    def local_version(self) -> tuple[str | None, str | None]:
        """Read version metadata from the project, never from Git tags."""
        return detect_local_version(self.root)

    def _normalize_version(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if value.lower().startswith("version"):
            value = value.split("=", 1)[-1].strip()
        match = re.search(r"\bv?(\d+\.\d+\.\d+)\b", value)
        return f"v{match.group(1)}" if match else None

    def _check_tools(self) -> None:
        self.run("rev-parse", "--is-inside-work-tree")

    def run(self, *args: str, check: bool = True, strip: bool = True) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=self.root, text=True, capture_output=True
        )
        if check and proc.returncode:
            detail = proc.stderr.strip() or proc.stdout.strip() or "git command failed"
            raise GitError(detail)
        return proc.stdout.strip() if strip else proc.stdout

    def run_gh(self, *args: str) -> str:
        proc = subprocess.run(
            ["gh", *args], cwd=self.root, text=True, capture_output=True
        )
        if proc.returncode:
            detail = proc.stderr.strip() or proc.stdout.strip() or "gh command failed"
            raise GitError(detail)
        return proc.stdout.strip()

    def branch(self) -> str:
        return self.run("branch", "--show-current") or "(detached)"

    def remote(self) -> str:
        return self.run("remote", "get-url", "origin", check=False)

    def has_remote(self) -> bool:
        return bool(self.remote())

    def status_porcelain(self) -> str:
        return self.run("status", "--porcelain=v1", "-z", strip=False)

    def status_text(self) -> str:
        version, source = self.local_version()
        head = self.run("log", "-1", "--format=%h %s", check=False) or "(no commits yet)"
        upstream = self.run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False) or "(not configured)"
        dirty = self.status_porcelain()
        entries = parse_porcelain(dirty)
        counts = count_changes(entries)
        out = ["\nPROJECT STATUS", "=" * 56, f"  Project       {self.name}", *inventory_lines(self.root),
               f"  Git branch    {self.branch()}", f"  Remote        {self.remote() or '(not configured)'}",
               f"  Upstream      {upstream}", f"  Working tree  {'DIRTY' if entries else 'CLEAN'} ({len(entries)} changed path(s))",
               f"  Version       {version or '(not detected)'}" + (f" ({source})" if source else ""),
               f"  Last commit   {head}", "", "CHANGE COUNTS",
               f"  Modified      {counts['modified']}", f"  Added         {counts['added']}",
               f"  Deleted       {counts['deleted']}", f"  Untracked     {counts['untracked']}"]
        if upstream != "(not configured)":
            counts_text = self.run("rev-list", "--left-right", "--count", f"HEAD...{upstream}", check=False).split()
            if len(counts_text) == 2 and all(x.isdigit() for x in counts_text):
                out.append(f"  Ahead/behind  {counts_text[0]} ahead / {counts_text[1]} behind")
        return "\n".join(out)

    def undo_last_commit(self) -> str:
        """Safely undo the latest commit by creating a revert commit.

        Requires a clean working tree; never rewrites shared history.
        """
        if self.status_porcelain():
            raise GitError("Undo requires a clean working tree. Commit or save local changes first.")
        if self.run("rev-parse", "--verify", "HEAD", check=False) == "":
            raise GitError("There is no commit to undo.")
        if self.run("rev-parse", "--is-shallow-repository", check=False) == "true":
            # Revert itself works on shallow repositories, so no special handling is needed.
            pass
        subject = self.run("log", "-1", "--pretty=%s")
        self.run("revert", "--no-edit", "HEAD")
        return subject

    def redo_last_undo(self) -> str:
        """Redo an undo by reverting the current HEAD when it is a revert commit."""
        if self.status_porcelain():
            raise GitError("Redo requires a clean working tree. Commit or save local changes first.")
        subject = self.run("log", "-1", "--pretty=%s", check=False)
        if not subject.lower().startswith("revert "):
            raise GitError("No immediately preceding undo/revert commit was detected at HEAD.")
        self.run("revert", "--no-edit", "HEAD")
        return subject

    def tracked_worktree_changes(self) -> list[str]:
        """List tracked files with unstaged worktree changes (safe restore candidates)."""
        raw = self.run("diff", "--name-only")
        return [line for line in raw.splitlines() if line]

    def restore_tracked_worktree_file(self, relative_path: str) -> None:
        """Discard unstaged changes to one tracked file after caller confirmation."""
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise GitError("Refusing unsafe file path; choose a tracked path inside this repository.")
        tracked = set(self.run("diff", "--name-only").splitlines())
        if relative_path not in tracked:
            raise GitError("File has no unstaged tracked changes. Staged and untracked files are not discarded here.")
        self.run("restore", "--worktree", "--", relative_path)

    def scan_text(self) -> str:
        raw = self.status_porcelain()
        entries = parse_porcelain(raw)
        lines = [f"{code} {path}" + (f" -> {original}" if original else "") for code, path, original in entries]
        change_counts = count_changes(entries)
        counts = {**change_counts, "other": 0}
        version, source = self.local_version()
        head = self.run("log", "-1", "--format=%h %s", check=False) or "(no commits yet)"
        out = ["\nREPOSITORY FILE SCAN", "=" * 56, *inventory_lines(self.root),
               f"  Git branch    {self.branch()}", f"  Remote        {self.remote() or '(not configured)'}",
               f"  Version       {version or '(not detected)'}" + (f" ({source})" if source else ""),
               f"  Last commit   {head}", f"  Changed files {len(entries)}", "", "CHANGE SUMMARY",
               f"  Modified      {counts['modified']}", f"  Added         {counts['added']}",
               f"  Deleted       {counts['deleted']}", f"  Other         {counts['other']}", "", "CHANGED PATHS"]
        out.extend(f"  {line}" for line in lines) if lines else out.append("  ✓ No tracked or untracked changes detected.")
        return "\n".join(out)

    def add_all(self) -> None:
        self.run("add", "-A")

    def commit(self, message: str) -> None:
        self.run("commit", "-m", message)

    def push(self) -> None:
        if not self.has_remote():
            raise GitError("No origin remote configured. PUSH requires a remote.")
        self.run("push", "origin", self.branch())

    def pull(self) -> None:
        self.run("pull", "--ff-only")

    def fetch(self) -> None:
        self.run("fetch", "origin")

    def force_sync(self) -> None:
        branch = self.branch()
        self.run("reset", "--hard", f"origin/{branch}")
        self.run("clean", "-fd")

    def latest_tag(self) -> str | None:
        tag = self.run("describe", "--tags", "--abbrev=0", check=False)
        return tag or None

    def commits_since(self, tag: str) -> list[str]:
        return self.run("log", f"{tag}..HEAD", "--pretty=format:%s", check=False).splitlines()

    def tag_exists(self, version: str) -> bool:
        return bool(self.run("tag", "--list", version))

    def remote_tag_exists(self, version: str) -> bool:
        """Check remote tag state without confusing transport errors with absence.

        A successful ``ls-remote`` with empty output means the tag is absent.
        Any command failure (authentication, DNS, network, or remote error) is
        raised as GitError so destructive callers fail closed with an accurate
        explanation instead of treating unknown state as a missing tag.
        """
        if not self.has_remote():
            raise GitError("No origin remote configured; cannot verify remote tag state.")
        return bool(self.run("ls-remote", "--tags", "--refs", "origin", f"refs/tags/{version}"))

    def github_release_exists(self, version: str) -> bool:
        """Return whether gh can find an existing release; fail closed if state is unknown."""
        try:
            proc = subprocess.run(
                ["gh", "release", "view", version], cwd=self.root, text=True, capture_output=True
            )
        except FileNotFoundError as exc:
            raise GitError("GitHub CLI 'gh' is not installed; cannot safely verify release state.") from exc
        if proc.returncode == 0:
            return True
        detail = (proc.stderr or proc.stdout).lower()
        if "not found" in detail or "release not found" in detail:
            return False
        raise GitError((proc.stderr or proc.stdout).strip() or "Unable to verify GitHub Release state.")

    def tag(self, version: str) -> None:
        if self.tag_exists(version):
            raise GitError(f"Tag {version} already exists locally. Refusing to overwrite it.")
        self.run("tag", "-a", version, "-m", f"Release {version}")

    def push_tag(self, version: str) -> None:
        self.run("push", "origin", version)

    def github_release(self, version: str, notes: str) -> None:
        self.run_gh("release", "create", version, "--title", version, "--notes", notes)

    def github_releases(self) -> list[dict[str, object]]:
        """List GitHub Releases with stable fields; fail closed on API/CLI errors."""
        raw = self.run_gh(
            "release", "list", "--limit", "100",
            "--json", "tagName,name,isDraft,isPrerelease,publishedAt",
        )
        try:
            data = json.loads(raw or "[]")
        except json.JSONDecodeError as exc:
            raise GitError("GitHub CLI returned invalid release-list JSON.") from exc
        if not isinstance(data, list):
            raise GitError("GitHub CLI returned an unexpected release-list response.")
        return [item for item in data if isinstance(item, dict)]

    def github_release_details(self, version: str) -> str:
        return self.run_gh("release", "view", version)

    def delete_github_release(self, version: str) -> None:
        """Delete the GitHub Release object only; tags are deliberately untouched."""
        self.run_gh("release", "delete", version, "--yes")

    def local_tags(self) -> list[str]:
        return self.run("tag", "--list").splitlines()

    def delete_local_tag(self, version: str) -> None:
        if not self.tag_exists(version):
            raise GitError(f"Local tag {version} does not exist.")
        self.run("tag", "-d", version)

    def delete_remote_tag(self, version: str) -> None:
        if not self.has_remote():
            raise GitError("No origin remote configured; cannot delete a remote tag.")
        if not self.remote_tag_exists(version):
            raise GitError(f"Remote tag {version} does not exist.")
        self.run("push", "origin", "--delete", version)


def find_changelogs(root: Path) -> list[Path]:
    """Discover changelog/history files by exact basename patterns, pruning skipped dirs."""
    import os
    extensions = {".md", ".mdx", ".rst", ".txt", ".adoc", ".asciidoc"}
    pattern = re.compile(r"^(?:changelog|change-log|changes|history|release-notes?|version-history|whatsnew|news)(?:[-_.]v?\d+(?:\.\d+){0,2})?$", re.I)
    found: list[Path] = []
    root = Path(root)
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP_DIRS and not (Path(current) / d).is_symlink())
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.suffix.lower() not in extensions or path.is_symlink():
                continue
            stem = path.stem.replace(" ", "-").replace("_", "-")
            if pattern.fullmatch(stem):
                found.append(path)

    def rank(path: Path):
        name = path.stem.lower().replace("_", "-").replace(" ", "-")
        return (0 if name.startswith("changelog") or name.startswith("change-log") else 1 if name.startswith("release-note") else 2 if name.startswith(("history", "changes")) else 3, name, path.relative_to(root).as_posix().lower())
    return sorted(found, key=rank)


def auto_commit_message(repo: "GitRepo") -> str:
    """Infer a concise commit subject from changed paths and recent project documentation."""
    status = repo.run("status", "--porcelain=v1", "-z", "-uall", check=False, strip=False)
    paths = []
    for _code, path, original in parse_porcelain(status):
        raw = path or original
        if raw and raw not in paths:
            paths.append(raw)
    if not paths:
        return "chore: update project"

    # Project docs carry intent; changelog entries and README summaries are stronger
    # signals than generic filesystem labels. Never invent a feature claim.
    doc_text = ""
    for rel in ("docs/CHANGELOG.md", "CHANGELOG.md", "README.md", "docs/README.md"):
        file = repo.root / rel
        if file.is_file():
            try:
                doc_text += "\n" + file.read_text(encoding="utf-8")[:12000]
            except (OSError, UnicodeError):
                pass
    changelogs = find_changelogs(repo.root)
    if changelogs:
        for file in changelogs[:4]:
            try:
                content = file.read_text(encoding="utf-8")
                headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", content)
                if headings:
                    doc_text += "\n" + " ".join(headings[:12])
            except (OSError, UnicodeError):
                pass

    def is_test_path(path: str) -> bool:
        parts = Path(path).parts
        name = Path(path).name.lower()
        return any(part.lower() in {"tests", "test", "__tests__"} for part in parts[:-1]) or name.startswith("test_") or name.endswith("_test.py") or name.endswith(".test.py") or name.endswith(".spec.py")

    # Determine intent from actual changed files; avoid substring guesses such as
    # "test" in latest.json or "page" in homepage.html.
    if paths and all(is_test_path(p) for p in paths):
        prefix = "test"
    elif all(p.lower().endswith((".md", ".rst", ".txt", ".adoc", ".asciidoc")) or "docs/" in p.lower() for p in paths):
        prefix = "docs"
    else:
        prefix = "chore"

    # Prefer a useful changelog subsection label when available, but don't copy long prose.
    candidates = re.findall(r"(?im)^#{2,4}\s+(Added|Changed|Fixed|Removed|Features?|Bug fixes?)\s*$", doc_text)
    label_map = {"added": "implement project updates", "changed": "update project behavior",
                 "fixed": "fix project issues", "removed": "remove obsolete project parts",
                 "feature": "implement project features", "features": "implement project features",
                 "bug fixes": "fix project issues"}
    if candidates:
        detail = label_map.get(candidates[0].lower(), "update project")
    else:
        # Summarize changed top-level areas instead of using the old generic default.
        areas = []
        for path in paths:
            parts = Path(path).parts
            area = parts[0] if len(parts) > 1 else parts[0]
            if area not in areas and area not in {".gitignore", "README.md", "CHANGELOG.md"}:
                areas.append(area)
        detail = ("update " + ", ".join(areas[:2])) if areas else "refresh project documentation"
    detail = re.sub(r"\s+", " ", detail).strip().lower()
    return f"{prefix}: {detail}"[:72].rstrip()
