# Plan — HIKARI 0.8.1 First Release Without Version Metadata

## Context
The 0.8.0 source increment added productivity commands, but release creation still aborted if `local_version()` returned no version. That prevented a first Git tag for otherwise valid projects.

## Acceptance criteria
- A clean Git project with commits but no detectable version can create a first release.
- Interactive flow offers `v0.1.0`, custom SemVer, and cancellation.
- `release --yes` selects `v0.1.0` if no version exists.
- Existing projects retain their quick/current/custom release choices.
- No version metadata is written into the target project.
- Duplicate tags, clean-tree checks, release-note generation, and remote guards remain intact.
- Canonical tests and exact extracted ZIP preflight pass.

## Implementation and verification
Implemented in `src/hikari/cli.py`; regression coverage in `tests/test_release_modes.py`. Exact artifact validation results are recorded in `docs/RELEASE-MANIFEST.md` after packaging. Authenticated GitHub publication is environment-dependent and is not claimed unless run.
