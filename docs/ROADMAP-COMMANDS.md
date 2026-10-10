# HIKARI command additions

## Foundation and productivity

- `hikari --version` prints the package and Python versions.
- `hikari doctor [PATH]` checks Python, Git, GitHub CLI authentication, target writability, and HIKARI support paths.
- `hikari completion bash|zsh|fish` prints shell completion definitions.
- `hikari init NAME --template python-cli|python-lib|empty [--git]` scaffolds a project. Existing targets are never overwritten.
- `hikari PATH status --json` emits a machine-readable status snapshot.
- `hikari PATH watch [--interval SECONDS]` refreshes status every 2 seconds by default (valid range 1–60).
- `hikari PATH notes add TEXT|list|show|edit|clear` stores project notes under `~/.hikari/notes` (or `$HIKARI_HOME`).
- `hikari PATH time start|stop|status|report [--week|--month]` tracks local work sessions under `~/.hikari/time`.

## Additional commands

- `diff` supports `--staged`/`--cached`, `--stat`, and an optional file path.
- `conflict` offers ours/theirs/editor/stage actions for Git conflict files. Review choices carefully.
- `repos add|list|status|remove` maintains a local registry. `sync-all` currently reports that bulk sync requires manual per-repository review.
- `pr`, `issue`, and `actions` delegate to the authenticated `gh` CLI; destructive PR actions require confirmation.
- `hikari PATH release notes --from REF --to REF [--template keepachangelog|simple|github] [--write]` generates notes from Git commit subjects. `--from-last-tag` selects the previous tag.
- `hikari.plugins` exposes a local plugin base class and loader. Plugins execute arbitrary Python; only install trusted code. Set `HIKARI_NO_PLUGINS=1` to disable loading.
- `release notes` generation is available as `hikari.commands.release_notes.generate()` for scripted use.

All new support files use the standard library and keep per-project notes/timers outside repositories. `NO_COLOR` disables the shared palette. Existing commands remain available.
