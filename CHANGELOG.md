# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/), versions follow [SemVer](https://semver.org/).

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
