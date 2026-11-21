# Design · task-cleaner

> Public design notes. The implementation lives in `scripts/registry.py`; behavior is locked by `scripts/test_registry.py`.

## Why this exists

AI agents leave files behind, and almost no agent deletes them when a task ends:

| Platform | What "delete task" actually does | Task files |
|---|---|---|
| Doubao Work | removes the task record | kept on disk |
| WorkBuddy | offers an opt-in "delete files too" inside a confirm dialog | kept unless ticked |
| DSH (DeepSeek Harness) | unregisters the workspace / archives the session | kept on disk |

The result: artifacts and junk sit in the same folder, nobody dares to delete, and the real space hogs (package caches) are never touched.

So the goal is **not "delete harder"** — it is **"tell things apart, then let the human pick"**.

## Design principles

1. **Zero migration** — registration never moves, renames or rewrites a file.
2. **Zero automation** — deletion happens only when the user says so. No turn hooks, no cron.
3. **Global is read-only** — interpreters, sandbox envs, connector runtimes, skill dirs and tool-result copies are never deleted.
4. **Recycle first** — every deletion is a same-volume rename into a 30-day trash.
5. **No guessing** — classification is by `kind` and by position, never by reading content.

## Registry layout

```text
<project root>/
├── agent-registry.json      # machine-readable source of truth
├── agent-registry.md        # human-readable mirror, regenerated on save
├── agent-registry.log       # one JSONL line per action
└── subproject/
    └── agent-registry.json  # optional per-subproject registry
```

- The nearest registry upward from the path you act on is the one used.
- A subproject registry may only delete entries inside its own root.
- `status --all` walks `**/agent-registry.json` for an aggregate board.

## Lifecycle

```
work  → register(path, kind, task)        # writes JSON only
user says "clean up" → plan               # numbered candidate table, no changes
user picks numbers  → remove --pick N --yes
                    → .agent-trash/<batch>/   (30 days, restorable)
user asks to free space → purge --yes     # only expired batches
```

## Four lists

| List | Members | Behavior |
|---|---|---|
| **A candidates** | `temp` / `script` / `cache` / `log`, project-local `dependency`; `artifact` only with `--include-artifacts` | shown in the numbered table |
| **B protected** | `.git`, `.vscode`, `.idea`, lock/manifest files, README, user docs, `shared=true` entries | never auto-candidates |
| **C forbidden** | interpreter homes, sandbox envs, connector runtime, skill install dirs, session traces, system paths | no delete path at all |
| **D global rebuildables** | pip cache, npm cache (local/roaming) | separate `gplan` / `gclean` / `gpurge` |

## Safety checks

1. Path must resolve inside the project root — checked at `register` and again at `remove`.
2. Absolute paths and `..` traversal in the JSON are rejected (`_entry_parts`).
3. Symlinks and Windows junctions are refused, never followed.
4. `remove` requires `--yes`; the plan's numbering must match the current registry hash.
5. A single entry larger than 2 GB requires `--force`.
6. Physical deletion happens only in `purge`, and only inside the trash directory.
7. Restore never overwrites: an existing target is renamed to `*.conflict-<ts>` first.
8. Global caches are moved by same-volume rename; on failure the tool stops and prints the official command instead of deleting.

## CLI surface

`init`, `register`, `status`, `list`, `plan`, `remove`, `restore`, `purge`, `doctor`, `gplan`, `gclean`, `gpurge`.
Every command supports `--json`; `plan` never mutates the filesystem.

## Known limits

- Not a garbage classifier: if it was never registered, it is not in the table.
- No cross-volume moves; the trash must live inside the same project root.
- Registration is per project: cleaning one project never touches another.
- Python 3.8+ with the standard library only; no network access.

## Version history

| Version | Change |
|---|---|
| v0.1 | directory contract with auto-sweep (dropped) |
| v0.2 | replaced by sidecar registration; all automation removed |
| v0.3 | added the global-cache group as a separate entry point |
| v0.4 | named `task-cleaner`; two-level registry (root + subprojects) |
