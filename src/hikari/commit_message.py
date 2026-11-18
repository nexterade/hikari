"""Deterministic, offline commit-message suggestions.

No network, no AI service, nothing leaves the machine. The engine reads what
Git already knows (status, a zero-context diff, recent subjects) and applies
transparent rules:

* file *kind* (added / deleted / renamed / modified) -> verb
* file *category* (source, test, docs, ci, build, config, asset) -> Conventional Commit type
* real signals only: ``fix`` words the author wrote in added lines, brand-new
  source files, new public functions/classes, version bumps, CHANGELOG entries
* the repository's own history decides the style (Conventional Commits vs plain
  sentences, with or without scopes)

It never invents intent: when nothing specific is detected it falls back to an
honest ``chore: update <files>``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MAX_SUBJECT = 72
_DIFF_LIMIT = 400_000
_READ_LIMIT = 64_000
_MAX_UNTRACKED_READS = 25
_MAX_FILES_ANALYSED = 500

SOURCE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".c", ".h",
    ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".sh", ".bash", ".zsh", ".lua", ".dart",
    ".vue", ".svelte", ".css", ".scss", ".less", ".html", ".htm", ".sql",
}
DOC_EXT = {".md", ".mdx", ".rst", ".adoc", ".asciidoc", ".txt"}
ASSET_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".mp3", ".wav", ".ogg", ".mp4",
    ".webm", ".ttf", ".otf", ".woff", ".woff2", ".pdf",
}
CONFIG_EXT = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf"}
DEP_NAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "pipfile", "pipfile.lock", "poetry.lock", "package.json",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "cargo.toml", "cargo.lock", "go.mod", "go.sum",
    "gemfile", "gemfile.lock", "composer.json", "composer.lock", "pom.xml", "build.gradle",
}
BUILD_NAMES = DEP_NAMES | {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "makefile", "cmakelists.txt"}
VERSION_FILES = {"version", "version.txt", "version.py", "_version.py", "__init__.py", "pyproject.toml",
                 "package.json", "cargo.toml", "setup.py", "setup.cfg"}
LOCK_NAMES = {"pipfile.lock", "poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "cargo.lock",
              "go.sum", "gemfile.lock", "composer.lock"}
CHANGELOG_STEMS = {"changelog", "changes", "history", "release-notes", "release_notes", "releases", "news"}
SECRETISH_EXT = {".pem", ".key", ".p12", ".pfx", ".kdbx"}

_TEST_RE = re.compile(r"^(test_.*|.*_test\.\w+|.*\.(test|spec)\.\w+|conftest\.py)$", re.I)
_FIX_RE = re.compile(r"\b(fix(?:e[sd]|ing)?|bugs?|crash(?:es|ed)?|typos?|regressions?|workarounds?|hotfix)\b", re.I)
_VERSION_LINE_RE = re.compile(
    r"""^\s*["']?(?:__version__|version)["']?\s*[:=]\s*["']?v?(\d+\.\d+\.\d+[\w.+-]*)""", re.I)
_BARE_VERSION_RE = re.compile(r"^\s*v?(\d+\.\d+\.\d+[\w.+-]*)\s*$")
_CONV_RE = re.compile(r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(?:\((?P<scope>[^)]+)\))?!?:\s")
_SYMBOL_RES = [
    re.compile(r"^(?:async\s+)?def\s+([A-Za-z]\w*)\s*\("),
    re.compile(r"^class\s+([A-Za-z]\w*)"),
    re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z]\w*)"),
    re.compile(r"^export\s+(?:const|class)\s+([A-Za-z]\w*)"),
    re.compile(r"^func\s+([A-Za-z]\w*)\s*\("),
    re.compile(r"^pub\s+(?:async\s+)?fn\s+([A-Za-z]\w*)"),
]
_PAST_TO_IMPERATIVE = {
    "added": "add", "fixed": "fix", "removed": "remove", "changed": "change", "updated": "update",
    "improved": "improve", "renamed": "rename", "replaced": "replace", "introduced": "introduce",
    "implemented": "implement", "documented": "document", "deprecated": "deprecate", "adds": "add",
    "fixes": "fix", "removes": "remove", "updates": "update",
}
_GENERIC_HEADINGS = {"added", "changed", "fixed", "removed", "features", "feature", "bug fixes", "bug fix",
                     "deprecated", "security", "unreleased", "improvements"}
_PARENT_NOISE = {"", ".", "src", "lib", "app", "source", "packages"}


@dataclass
class Change:
    path: str
    kind: str                    # added | deleted | renamed | modified
    category: str
    original: str | None = None
    added_lines: list[str] = field(default_factory=list)
    removed: int = 0
    symbols: list[str] = field(default_factory=list)


@dataclass
class CommitSuggestion:
    subject: str
    body: str = ""
    type: str = "chore"
    scope: str | None = None
    style: str = "conventional"
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def full(self) -> str:
        return self.subject + (f"\n\n{self.body}" if self.body else "")


# ───────────────────────── classification ─────────────────────────

def _is_test(p: PurePosixPath) -> bool:
    dirs = {x.lower() for x in p.parts[:-1]}
    return bool(dirs & {"tests", "test", "__tests__", "spec"}) or bool(_TEST_RE.match(p.name))


def classify(path: str) -> str:
    """Return one of: ci, test, build, docs, asset, source, config, other."""
    p = PurePosixPath(path.replace("\\", "/"))
    name, lower = p.name, p.name.lower()
    parts = [x.lower() for x in p.parts]
    ext = p.suffix.lower()
    if parts[:2] == [".github", "workflows"] or parts[0] == ".circleci" or lower in {".gitlab-ci.yml", ".travis.yml", "jenkinsfile"}:
        return "ci"
    if _is_test(p):
        return "test"
    if lower in BUILD_NAMES or re.fullmatch(r"requirements[-_.\w]*\.txt", lower):
        return "build"
    if ext in DOC_EXT or parts[0] in {"docs", "doc"} or lower in {"license", "licence", "copying", "authors", "notice"}:
        return "docs"
    if ext in ASSET_EXT:
        return "asset"
    if ext in SOURCE_EXT:
        return "source"
    if lower in {"version", ".gitignore", ".gitattributes", ".editorconfig"} or ext in CONFIG_EXT or name.startswith("."):
        return "config"
    return "other"


def _kind(code: str, original: str | None) -> str:
    if "R" in code or "C" in code or original:
        return "renamed"
    if "D" in code:
        return "deleted"
    if code == "??" or "A" in code:
        return "added"
    return "modified"


def _is_changelog(path: str) -> bool:
    p = PurePosixPath(path)
    return p.suffix.lower() in DOC_EXT and p.stem.lower().replace(" ", "-") in CHANGELOG_STEMS


def _is_secretish(path: str) -> bool:
    p = PurePosixPath(path)
    lower = p.name.lower()
    return (lower == ".env" or (lower.startswith(".env.") and "example" not in lower and "sample" not in lower)
            or p.suffix.lower() in SECRETISH_EXT or lower.startswith("id_rsa") or lower.startswith("id_ed25519"))


# ───────────────────────── git data collection ─────────────────────────

def _parse_diff(text: str) -> dict[str, tuple[list[str], int]]:
    """Map path -> (added lines, removed count) from a unified=0 diff."""
    files: dict[str, tuple[list[str], int]] = {}
    in_header = False
    old_path = ""
    cur: str | None = None
    for line in text[:_DIFF_LIMIT].splitlines():
        if line.startswith("diff --git "):
            in_header, cur, old_path = True, None, ""
            continue
        if in_header:
            if line.startswith("--- "):
                old_path = line[4:].strip("\t").strip('"')
                old_path = old_path[2:] if old_path.startswith("a/") else old_path
            elif line.startswith("+++ "):
                new = line[4:].strip("\t").strip('"')
                new = new[2:] if new.startswith("b/") else new
                cur = old_path if new == "/dev/null" else new
                files.setdefault(cur, ([], 0))
            elif line.startswith("@@"):
                in_header = False
            continue
        if cur is None:
            continue
        added, removed = files[cur]
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            files[cur] = (added, removed + 1)
    return files


def _extract_symbols(lines: list[str]) -> list[str]:
    seen: list[str] = []
    for line in lines:
        for rx in _SYMBOL_RES:
            m = rx.match(line)   # top-level only: indented methods never match
            if m:
                name = m.group(1)
                if not name.startswith("_") and name not in seen:
                    seen.append(name)
                break
    return seen


def _read_new_file(root: Path, rel: str) -> list[str]:
    try:
        path = root / rel
        if not path.is_file() or path.is_symlink():
            return []
        data = path.read_bytes()[:_READ_LIMIT]
        if b"\0" in data:
            return []
        return data.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        return []


def collect_changes(repo) -> list[Change]:
    from .git import parse_porcelain
    status = repo.run("status", "--porcelain=v1", "-z", "-uall", check=False, strip=False)
    if "\0" not in status and "\n" in status:      # tolerate newline-separated fakes/legacy callers
        status = "\0".join(status.splitlines())
    entries = parse_porcelain(status)[:_MAX_FILES_ANALYSED]
    changes: list[Change] = []
    seen: set[str] = set()
    for code, path, original in entries:
        rel = path or original
        if not rel or rel in seen:
            continue
        seen.add(rel)
        changes.append(Change(rel, _kind(code, original), classify(rel), original))
    if not changes:
        return changes
    diff_text = repo.run("-c", "core.quotepath=off", "diff", "HEAD", "--unified=0", "--no-color",
                         "--no-ext-diff", check=False, strip=False) or ""
    diff = _parse_diff(diff_text)
    reads = 0
    for ch in changes:
        if _is_secretish(ch.path):
            continue                                # never open anything that looks like a secret
        if ch.path in diff:
            ch.added_lines, ch.removed = diff[ch.path]
        elif ch.kind == "added" and ch.category in {"source", "docs", "config", "build"} and reads < _MAX_UNTRACKED_READS:
            ch.added_lines = _read_new_file(repo.root, ch.path)
            reads += 1
        if ch.category == "source" and not _is_test(PurePosixPath(ch.path)):
            ch.symbols = _extract_symbols(ch.added_lines)
    return changes


def _history_subjects(repo) -> list[str]:
    raw = repo.run("log", "-n", "30", "--format=%s", check=False) or ""
    return [s.strip() for s in raw.split("\n") if s.strip() and "\0" not in s]


def detect_style(subjects: list[str]) -> tuple[str, bool, bool]:
    """Return (style, use_scope, lowercase) learned from recent commit subjects."""
    subs = [s for s in subjects if not s.startswith(("Merge ", "Revert "))]
    if len(subs) < 5:
        return "conventional", False, True
    conv = [m for m in (_CONV_RE.match(s) for s in subs) if m]
    if len(conv) / len(subs) < 0.5:
        lower = sum(1 for s in subs if s[:1].islower()) / len(subs) >= 0.6
        return "plain", False, lower
    scoped = sum(1 for m in conv if m.group("scope"))
    return "conventional", scoped / len(conv) >= 0.25, True


# ───────────────────────── text helpers ─────────────────────────

def _fit(prefix: str, text: str, limit: int = MAX_SUBJECT) -> str:
    room = limit - len(prefix)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > room:
        cut = text[:room]
        if text[room] != " " and " " in cut:
            cut = cut[: cut.rfind(" ")]
        text = cut.rstrip(" ,;:-—(/")
    return (prefix + text).rstrip()


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]{1,3}", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _imperative(text: str) -> str:
    words = text.split(" ", 1)
    first = words[0]
    low = first.lower()
    if low in _PAST_TO_IMPERATIVE:
        first = _PAST_TO_IMPERATIVE[low]
    elif first[:1].isupper() and first[1:].islower():   # keep acronyms / identifiers untouched
        first = low
    return first + (" " + words[1] if len(words) > 1 else "")


def _intent_type(text: str) -> str | None:
    w = text.split(" ", 1)[0].lower().strip(":")
    if w in {"fix", "fixed", "fixes", "bugfix", "hotfix"}:
        return "fix"
    if w in {"add", "added", "adds", "new", "support", "implement", "implemented", "introduce", "introduced"}:
        return "feat"
    if w in {"refactor", "refactored", "restructure", "simplify"}:
        return "refactor"
    if w in {"optimize", "optimise", "speed"}:
        return "perf"
    if w in {"document", "documented", "docs"}:
        return "docs"
    return None


def _changelog_intent(changes: list[Change]) -> tuple[str, str | None] | None:
    """Use what the author wrote in the CHANGELOG entry they are committing."""
    bullets: list[str] = []
    title = ""
    for ch in changes:
        if not _is_changelog(ch.path) or ch.kind == "deleted":
            continue
        for line in ch.added_lines:
            m = re.match(r"^#{1,4}\s+(.+)$", line)
            if m and not title:
                t = _clean_markdown(m.group(1))
                t = re.sub(r"^\[?v?\d+\.\d+\.\d+[\w.+-]*\]?\s*(?:\(.*?\))?\s*[—–:-]*\s*", "", t)
                t = re.sub(r"^unreleased\s*[—–:-]*\s*", "", t, flags=re.I)
                if t and t.lower() not in _GENERIC_HEADINGS:
                    title = t
                continue
            b = re.match(r"^\s*[-*+]\s+(.+)$", line)
            if b:
                bullets.append(_clean_markdown(b.group(1)))
    def first_clause(s: str) -> str:
        s = re.split(r"\.\s|\s[—–]\s|;\s|:\s", s, maxsplit=1)[0]
        return s.rstrip(" .,;:")
    pick = ""
    if bullets:
        cand = first_clause(bullets[0])
        pick = cand if len(cand) <= 60 or not title else title
    elif title:
        pick = title
    if not pick:
        return None
    pick = _imperative(pick)
    return pick, _intent_type(pick)


def _version_bump(changes: list[Change]) -> str | None:
    carriers = [c for c in changes if PurePosixPath(c.path).name.lower() in VERSION_FILES and c.kind == "modified"]
    if not carriers:
        return None
    for c in changes:
        n = PurePosixPath(c.path).name.lower()
        if not (n in VERSION_FILES or n in LOCK_NAMES or _is_changelog(c.path) or n.startswith("readme")
                or n.startswith("release")):
            return None
    for c in carriers:
        is_bare = PurePosixPath(c.path).name.lower() in {"version", "version.txt"}
        for line in c.added_lines:
            m = (_BARE_VERSION_RE if is_bare else _VERSION_LINE_RE).match(line)
            if m:
                return "v" + m.group(1)
    return None


# ───────────────────────── composition ─────────────────────────

def _display_names(changes: list[Change]) -> list[str]:
    raw: list[tuple[str, str]] = []
    for ch in changes:
        p = PurePosixPath(ch.path)
        raw.append((p.name, ch.path))
    names: list[str] = []
    for base, path in raw:
        dupes = sum(1 for b, _ in raw if b == base) > 1
        p = PurePosixPath(path)
        name = f"{p.parent.name}/{base}" if dupes and p.parent.name else base
        if name not in names:
            names.append(name)
    return names


def _object_phrase(changes: list[Change]) -> str:
    names = _display_names(changes)
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    if len(names) == 3:
        return f"{names[0]}, {names[1]} and {names[2]}"
    parents = {str(PurePosixPath(c.path).parent) for c in changes}
    common = ""
    if len(parents) == 1:
        common = parents.pop()
    else:
        tops = {PurePosixPath(c.path).parts[0] for c in changes if len(PurePosixPath(c.path).parts) > 1}
        if len(tops) == 1 and all(len(PurePosixPath(c.path).parts) > 1 for c in changes):
            common = tops.pop()
    where = f" in {common}" if common and common != "." else ""
    return f"{len(names)} files{where}"


def _scope_for(primary: list[Change]) -> str | None:
    if not primary:
        return None
    if len(primary) == 1:
        p = PurePosixPath(primary[0].path)
        stem = p.stem.lower() if primary[0].category in {"source", "test", "docs"} else p.parent.name.lower()
        return stem if stem and stem not in _PARENT_NOISE else None
    parents = {PurePosixPath(c.path).parent.name.lower() for c in primary}
    if len(parents) == 1:
        only = parents.pop()
        return only if only not in _PARENT_NOISE else None
    return None


def _verb_for(primary: list[Change]) -> str:
    kinds = {c.kind for c in primary}
    if kinds == {"added"}:
        return "add"
    if kinds == {"deleted"}:
        return "remove"
    if kinds == {"renamed"}:
        return "rename"
    return "update"


def _decide_type(changes: list[Change], intent: str | None) -> tuple[str, str]:
    cats = {c.category for c in changes}
    if "source" in cats:
        fix_hits = [c for c in changes if c.category in {"source", "other", "config"} and c.kind != "added"
                    and any(_FIX_RE.search(l) for l in c.added_lines)]
        if fix_hits:
            return "fix", "'fix/bug/crash' wording found in added lines"
        if intent:
            return intent, "CHANGELOG entry in this change"
        src = [c for c in changes if c.category == "source"]
        if any(c.kind == "added" for c in src):
            return "feat", "new source file(s)"
        if any(c.symbols for c in src):
            return "feat", "new public function/class: " + ", ".join(s for c in src for s in c.symbols[:2])
        if all(c.kind == "deleted" for c in src):
            return "chore", "source files removed"
        if all(c.kind == "renamed" for c in src):
            return "refactor", "files renamed/moved only"
        return "chore", "source modified; no specific intent detected"
    for cat, typ in (("ci", "ci"), ("build", "build"), ("test", "test"), ("docs", "docs")):
        if cat in cats:
            return typ, f"{cat} files changed"
    return "chore", "config/other files changed"


def suggest_commit_message(repo) -> CommitSuggestion:
    changes = collect_changes(repo)
    if not changes:
        return CommitSuggestion("chore: update project", reasons=["no changed paths detected"])
    style, use_scope, lowercase = detect_style(_history_subjects(repo))
    reasons = [f"{len(changes)} file(s): " + ", ".join(
        f"{n} {k}" for k in ("added", "modified", "deleted", "renamed")
        if (n := sum(1 for c in changes if c.kind == k)))]

    bump = _version_bump(changes)
    intent = _changelog_intent(changes)
    scope: str | None = None
    if bump:
        typ, why, text, scope = "chore", "version file changed", f"bump version to {bump}", "release"
        reasons.append("version bump detected in a version file")
    else:
        typ, why = _decide_type(changes, intent[1] if intent else None)
        aux_cats = {"docs", "test", "config", "asset"}
        primary = [c for c in changes if c.category not in aux_cats] or changes
        if typ == "docs":
            primary = [c for c in changes if c.category == "docs"] or primary
        elif typ == "test":
            primary = [c for c in changes if c.category == "test"] or primary
        scope = _scope_for(primary)
        if typ == "build" and all(PurePosixPath(c.path).name.lower() in DEP_NAMES | LOCK_NAMES or
                                  re.fullmatch(r"requirements[-_.\w]*\.txt", PurePosixPath(c.path).name.lower())
                                  for c in primary):
            scope = "deps"
        symbols = [s for c in primary for s in c.symbols]
        if intent and "source" in {c.category for c in changes}:
            text = intent[0]
        elif symbols and any(c.kind != "added" for c in primary):
            shown = ", ".join(symbols[:2]) + (f" and {len(symbols) - 2} more" if len(symbols) > 2 else "")
            text = f"add {shown}"
        else:
            text = f"{_verb_for(primary)} {_object_phrase(primary)}"
            if len(primary) == 1 and primary[0].kind == "renamed" and primary[0].original:
                text = f"rename {PurePosixPath(primary[0].original).name} to {PurePosixPath(primary[0].path).name}"
            extras = [label for cat, label in (("test", "tests"), ("docs", "docs")) if
                      any(c.category == cat for c in changes) and typ not in {cat}]
            if extras and len(primary) <= 3:
                text += " with " + " and ".join(extras)
        reasons.append(f"type '{typ}': {why}")

    if typ == "fix" and re.match(r"(?i)^fix(?:es|ed)?\s+\S", text):
        text = text.split(" ", 1)[1]                     # "fix: fix x" -> "fix: x"
    if style == "plain":
        subject = _fit("", text)
        subject = subject[:1].lower() + subject[1:] if lowercase else subject[:1].upper() + subject[1:]
        reasons.append("style: plain sentences (learned from recent history)")
        scope = None
    else:
        prefix = f"{typ}({scope}): " if (use_scope and scope) else f"{typ}: "
        subject = _fit(prefix, text)
        if use_scope:
            reasons.append("style: Conventional Commits with scopes (learned from recent history)")
        else:
            scope = None

    body = ""
    if len(changes) >= 4:
        verbs = {"added": "add", "modified": "update", "deleted": "remove", "renamed": "rename"}
        lines = []
        for c in changes[:12]:
            lines.append(f"- {verbs[c.kind]} {c.path}" if c.kind != "renamed" or not c.original
                         else f"- rename {c.original} -> {c.path}")
        if len(changes) > 12:
            lines.append(f"- … and {len(changes) - 12} more file(s)")
        body = "\n".join(lines)
    warnings = [f"'{c.path}' looks like it may contain secrets — check .gitignore before committing."
                for c in changes if _is_secretish(c.path) and c.kind != "deleted"]
    return CommitSuggestion(subject, body, typ, scope, style, reasons, warnings)
