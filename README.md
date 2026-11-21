# task-cleaner

> Sidecar file registry for AI agents — record what a task produced, then delete only what the human picks.

**一句话**：AI 干完活，把文件登记到项目里；等你说"清理"时，它列一张带编号的表，你勾哪条它删哪条，删掉的进 30 天回收站。

不搬文件、不自动清理、不碰全局环境。

---

## Why

Agents rarely clean up after themselves, and platform behavior varies wildly:

| Platform | Deleting a task | Task files |
|---|---|---|
| Doubao Work | removes the task record | kept |
| WorkBuddy | opt-in "delete files too" in the confirm dialog | kept unless ticked |
| DSH | unregisters workspace / archives session | kept |
| Codex / Cursor / Claude Code | no concept of cleanup | kept |

So artifacts and scratch files pile up in the same folder, and the real space hogs (pip/npm caches) are never touched. `task-cleaner` separates the two jobs:

- **register** — a sidecar JSON + Markdown that records real paths, kinds, sizes, and owning task. Nothing moves.
- **clean up** — only on explicit instruction, with a numbered candidate list for the user to select.

## Features

- **Zero migration** — registering never moves, renames, or rewrites a file.
- **Zero automation** — no turn hooks, no cron. Deletion only on user command.
- **Numbered selection** — `plan` prints a table; the user replies "delete 2 and 5".
- **30-day trash** — deletion is a same-volume rename into `.agent-trash/`, restorable with `restore`.
- **Hard guardrails** — path-escape, symlink/junction, `..` traversal, protected files, oversized batches are all refused.
- **Global stays read-only** — interpreters, sandbox envs, connector runtimes, skill dirs are statistics only. Package caches get their own opt-in entry point.
- **Portable** — one Python file, standard library only, Python 3.8+, Windows/macOS/Linux.

## Quick start

```bash
git clone <this-repo> ~/skills/task-cleaner
cd ~/skills/task-cleaner

python scripts/registry.py init --root ~/projects/demo
python scripts/registry.py register --root ~/projects/demo \
    --path ~/projects/demo/artifacts/report.md --kind artifact --task t1
python scripts/registry.py plan   --root ~/projects/demo
python scripts/registry.py remove --root ~/projects/demo --pick "2,3" --yes
python scripts/registry.py status --root ~/projects/demo
```

`plan` output:

```text
[候选] 编号  类型        体积       路径
  1    dependency  279.0 MB    .venv           └ 风险：删除后需重装（下载/编译耗时）
  2    temp        12.0 MB     scratch/shot.png └ 风险：无
[保护] artifacts/report.md
```

## Commands

| Command | Purpose |
|---|---|
| `init --root <dir>` | create the registry pair (`root` or `--type sub`) |
| `register --path <p> --kind <k> --task <t>` | record a file or directory |
| `status [--all]` | size board, including read-only global stats |
| `list [--task] [--kind]` | list entries |
| `plan [--include-artifacts]` | numbered candidate table, changes nothing |
| `remove --pick 1,3 --yes` | move picks into the trash |
| `restore <batch>` | put a batch back |
| `purge [--older-than 30] --yes` | delete expired batches for real |
| `doctor [--all]` | dangling entries, expired batches, stale plans |
| `gplan` / `gclean --pick N --yes` / `gpurge --yes` | global rebuildable caches |

All commands accept `--json`.

### Kinds

| kind | typical content | candidate |
|---|---|---|
| `artifact` | reports, images, deliverables | only with `--include-artifacts` |
| `temp` | one-off screenshots, probes | yes |
| `script` | helper scripts written for the task | yes |
| `cache` | rebuildable local caches | yes |
| `log` | run logs | yes |
| `dependency` | project-local `.venv`, `node_modules` | yes (flagged "needs reinstall") |
| `data` / `config` | source material, config | no (protected) |

## Safety model

Candidates must resolve inside the project root. Symlinks and junctions are never followed. `.git`, lock files, manifests, READMEs, and `shared` entries are protected. `remove` needs `--yes` and a plan whose hash still matches the registry. Physical deletion only happens in `purge`, only inside `.agent-trash/`, only for expired batches. Restore renames conflicts to `*.conflict-<timestamp>` instead of overwriting.

Global environments and package-cache directories are **never** deleted by the task path. Caches are moved by same-volume rename through `gclean`; if the rename fails, the tool stops and prints the official command rather than deleting.

## Use with agents

Drop the folder into your agent's skills directory and the `SKILL.md` frontmatter does the triggering:

| Agent | Where |
|---|---|
| Doubao Work / any SKILL.md-compatible agent | `<agent_home>/skills/task-cleaner/` |
| Claude Code | `~/.claude/skills/task-cleaner/` |
| Codex / Cursor | repo-root `AGENTS.md` / `.cursorrules` (see `scripts/adapters/AGENTS.snippet.md`) |
| DSH | `~/.dsh/AGENTS.md` + project `AGENTS.md` |
| WorkBuddy | its skill directory |

The 30-line rule block in `scripts/adapters/AGENTS.snippet.md` is enough to keep an agent from over-cleaning: register, never self-clean, always ask first.

## Tests

```bash
python scripts/test_registry.py -v
```

13 tests across three groups: **zero migration** (file tree hashes unchanged after register/plan/status), **boundary rejection** (outside-root, system paths, protected files, `..` traversal, tampered plans, missing `--yes`, cross-project access), **restore round-trip** (three move/restore cycles with stable SHA-256, plus purge-then-restore failure).

## FAQ

**Why not just `pip cache purge`?**
It is irreversible. `gclean` renames cache contents into a same-volume trash so you can put them back within 30 days; if the rename is impossible it tells you to run the official command instead.

**Why 30 days?**
Long enough to catch a mistake, short enough that the trash does not become the new mess. `purge --older-than 1` is available when you need the space back immediately.

**Does it touch configs?**
No. It creates three files at the project root (`agent-registry.json`, `.md`, `.log`), plus `.agent-trash/` after the first deletion. Everything else stays where it was.

## License

MIT — see [LICENSE](LICENSE).
