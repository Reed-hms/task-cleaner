# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/), versions follow [SemVer](https://semver.org/).

## [1.0.1] - 2026-11-21

### Fixed
- Root-confinement false positive on canonical-path aliases. A project root spelled as an 8.3 short name (`C:\Users\RUNNER~1\...`) or through a symlinked prefix (`/var/...` → `/private/var/...`) made every in-root file look like a path escape, so `register` refused files that were legitimately inside the project. Path comparison is now canonicalised on both sides; entries are still stored as project-relative paths.
- `ubuntu-latest` (24.04) no longer ships Python 3.8, so the 3.8 job failed at `setup-python` before running anything. The matrix now pins host-specific combinations instead of multiplying every OS by every version.

### Added
- Two regression tests covering an aliased project root (symlink on POSIX, directory junction on Windows; skipped only where the OS forbids both).

## [1.0.0] - 2026-11-21

### Added
- Sidecar registry: `agent-registry.json` (source of truth) + `agent-registry.md` (human mirror) + `agent-registry.log` (audit).
- Two-level layout: one registry at the project root, optional ones per subproject.
- `init` / `register` / `status` / `list` / `plan` / `remove` / `restore` / `purge` / `doctor`.
- Numbered candidate table with per-entry risk notes; selection by number only.
- 30-day trash implemented as a same-volume rename; `restore` never overwrites.
- Global-cache group behind its own entry point: `gplan` / `gclean` / `gpurge` (pip and npm caches, same-volume trash, never part of task candidates).
- Hard guardrails: project-root confinement, `..`/absolute-path rejection, symlink and junction refusal, protected-file list, `--yes` requirement, plan-hash validation, 2 GB batch cap.
- 13 tests: zero migration, boundary rejection, restore round-trip.

### Notes
- Python 3.8+, standard library only, no network access.
- Deliberately no automatic cleanup: deletion only on explicit user instruction.
