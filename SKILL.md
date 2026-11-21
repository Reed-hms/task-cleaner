---
name: task-cleaner
description: 项目文件旁路登记与按指令清理技能。用于记录任务产出与过程文件（脚本、临时件、日志、依赖、产物）的真实路径与体积，并在用户明确要求"删除任务/清理过程文件"时，生成带编号的候选清单、由用户勾选后才移入 30 天回收站。不改动任何原有路径与配置，不自动清理、不挂定时任务。当用户提到任务产物清理、删除任务文件、清理临时文件、项目占空间、回收站还原、查看磁盘/缓存占用时使用。
license: MIT
---

# task-cleaner

**三条铁律，任何情况下不得违反：**

1. **零迁移** —— 只读登记，绝不移动、改名、改写任何原有文件或配置。
2. **零自动** —— 唯一触发删除的口令是用户明确说"删除 / 清理这些"。**绝不在任务结束时自行清理，绝不挂定时清理。**
3. **全局只读** —— 环境（anaconda、运行时 Python、sandbox_envs）、连接器运行时、技能目录、会话痕迹**永不删**；只有 pip/npm/浏览器缓存走独立入口 `gplan`。

## 30 秒工作流

```
① 干活时顺手登记（可选但推荐）：
   python scripts/registry.py register --path <真实路径> --kind <类型> --task <任务id>
   → 只写 agent-registry.json / .md，文件原地不动

② 用户说"删掉这次的过程文件"
   → plan 出候选表（带编号、体积、风险），先把表贴给用户
   → 等用户回复编号（如"删 2、5"）或"全删过程文件"

③ 按勾选执行
   → remove --pick 2,5 --yes    # 移入 .agent-trash，30 天可还原
   → 用户要彻底释放时才 purge --yes
```

## 命令速查

| 命令 | 用途 | 备注 |
|---|---|---|
| `init --root <目录>` | 建登记文件（项目根本层 / 子项目 `--type sub`） | 已有则拒绝，加 `--force` 覆盖 |
| `register --path --kind [--task] [--note]` | 登记一个文件/目录 | `kind` 见下表 |
| `status [--all] [--no-global]` | 体积看板（项目 + 全局只读统计） | `--all` 汇总 `**/agent-registry.json` |
| `list [--task] [--kind]` | 列出条目 | |
| `plan` | 生成候选表，编号 + 体积 + 风险 | **不改任何文件**；`--include-artifacts` 才纳入产物 |
| `remove --pick 1,3 --yes` | 按编号移入回收站 | 无 `--yes` 直接拒绝 |
| `restore <批次id>` | 还原批次 | 冲突先备份为 `*.conflict-时间` |
| `purge [--older-than 30] --yes` | 终删过期批次 | 默认只删已过期 |
| `doctor [--all]` | 一致性自检 | 悬空条目、过期批次、过期计划 |
| `gplan` / `gclean --pick N --yes` / `gpurge --yes` | 全局可重建缓存 | 同盘移入回收站，不进任务候选表 |

## kind 与候选资格

| kind | 典型内容 | 是否进候选 |
|---|---|---|
| `artifact` | 交付给用户的报告、图、表、成品代码 | 默认**不进**（保护），需 `--include-artifacts` 且用户点名 |
| `temp` | 一次性截图、探测脚本、中间转换件 | 进 |
| `script` | 任务期间写的辅助脚本 | 进 |
| `cache` | 可重建的本地缓存 | 进 |
| `log` | 运行日志 | 进 |
| `dependency` | 项目内 `.venv`、`node_modules` | 进，但标注"删除后需重装" |
| `data` / `config` | 原始素材、配置文件 | 不进（保护） |

自动保护：`.git`、`.vscode`、`.idea`、`requirements.txt`、`package.json`、`README`、`.gitignore` 等一律不列候选。

## 双层登记

- 最外层项目根放一份（例如 `<PROJECT_ROOT>/agent-registry.json`），子项目各放一份。
- 某路径上操作时**就近取最近的登记文件**；子项目登记只能删自己根内的条目，跨子项目一律拒绝。
- 汇总看板用 `status --all`。

## 给用户看的候选表长这样

```
[候选] 编号  类型        体积       路径
  1    dependency  279.0 MB    .venv            └ 风险：删除后需重装（下载/编译耗时）
  2    temp        12.0 MB     scratch/shot.png └ 风险：无
[保护] artifacts/report.md
```

先贴表，再等勾选。不要替用户做决定，也不要一次把全部候选删掉。

## 常见拒绝及处理

| 提示 | 原因 | 处理 |
|---|---|---|
| 路径不在本项目根内 | 越界 | 不能用本技能删项目外的东西；全局项只能 `gplan` |
| 受保护文件/目录 | `.git`、配置文件等 | 需用户手动处理，本技能不动 |
| 登记内容已变化，请重新 plan | 计划过期 | 重新 `plan` 再勾选 |
| 没有可用的清理计划 | 没跑 plan | 先 `plan` |
| 批次已被彻底删除 | 已 purge | 不可还原，只能重做 |

## 参考文档

- `references/registry-format.md` —— JSON 字段、MD 生成规则、去重与共享标记
- `references/safety.md` —— 四张名单、8 条硬校验、测试覆盖
- `references/platform-hooks.md` —— 豆包 / WorkBuddy / DSH / Codex 的接入文本

## 运行方式

纯标准库，无需安装依赖：

```
python scripts/registry.py status --root <PROJECT_ROOT>
```

Windows 下路径含空格要加引号；PowerShell 里 `--pick "1,3"` 建议整体加引号。
