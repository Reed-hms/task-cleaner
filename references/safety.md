# 安全规则

## 四张名单

| 名单 | 内容 | 行为 |
|---|---|---|
| **A 候选** | `temp`/`script`/`cache`/`log`、项目内 `dependency`；`artifact` 仅在 `--include-artifacts` 时 | 进候选表，等用户勾选 |
| **B 保护** | `.git`/`.vscode`/`.idea`、`requirements.txt`/`package.json`/`README`/`.gitignore` 等、`shared=true` 条目、`data`/`config` | 永不自动进候选；拒绝执行并说明原因 |
| **C 禁止** | `<PYTHON_HOME>`（anaconda/miniconda 等解释器目录）、`sandbox_envs`、连接器运行时、技能安装目录（`.skills` / 各 Agent 的 skills 目录）、`system/tool-results` 等会话痕迹、系统路径 | 无删除入口，只做只读统计 |
| **D 全局缓存** | pip 缓存、npm 缓存（Local/Roaming） | 仅 `gplan`/`gclean`/`gpurge`；不进任务候选表 |

## 8 条硬校验（代码位置：`guard()` / `_entry_parts()` / `remove()`）

1. 路径必须在项目根内；`register` 与 `remove` 各校验一次。
2. `_entry_parts()` 拒绝绝对路径与 `..` 穿越（即使 JSON 被手改成越界也会拦下）。
3. `guard()` 拒绝项目根自身、回收站自身、受保护目录/文件。
4. 符号链接 / Windows 联接点（junction）：**只拒绝、不递归**。
5. `remove` 必须带 `--yes`，否则直接抛错；`plan` 生成的编号映射必须与当前登记哈希一致，否则要求重新 `plan`。
6. 单条 >2 GB 需 `--force`；回收站目标已存在则跳过。
7. 物理删除只发生在 `purge`，且批次目录必须位于 `.agent-trash` 内。
8. 还原遇目标冲突 → 先改名为 `*.conflict-<时间戳>` 再还原，绝不覆盖。

## 反例（都必须被拒绝）

- `register --path ..\..\Windows\System32` → 越界
- `register --path <PYTHON_HOME>` → 越界（全局项只能统计）
- `remove --pick 1`（无 `--yes`） → 拒绝
- 手改 `agent-registry.json` 里的 `path` 为 `../x` → `_entry_parts` 抛错
- 手改编号后不重新 `plan` → 哈希不一致，拒绝
- 通过 junction 指到项目外 → `guard` 拒绝

## 测试覆盖（scripts/test_registry.py，13 项）

| 组 | 覆盖 |
|---|---|
| 零迁移 | `register`/`status`/`plan` 前后快照（路径、sha256、mtime）完全一致 |
| 越界拒绝 | 项目外登记、系统路径、根自身、受保护项、`..` 穿越、篡改计划、缺 `--yes`、子项目越权 |
| 还原往返 | 三轮"移走→还原"，sha256 一致；`purge` 后还原报错 |

## 边界声明

- 不处理项目外的东西（除 D 组白名单缓存）。
- 不判断"这是不是垃圾"，只按登记与名单。
- 不跨盘移动（回收站必须在项目内，同盘 rename）。
- 全局缓存清理用同盘 rename，失败即放弃并提示，绝不做递归删除兜底。
