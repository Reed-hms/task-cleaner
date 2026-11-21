# 平台接入

## 一段文本，四个平台通用

把下面这段注入到任意 agent 的系统提示 / 项目规则文件（30 行，足够约束行为）：

```markdown
## 文件登记与清理（task-cleaner）

- 你产出的文件，用一个命令登记，不要移动它们：
  `python <skill>/scripts/registry.py register --path <绝对或相对路径> --kind <artifact|script|data|temp|dependency|cache|log|config> --task <任务id>`
- **绝不在任务结束时自行清理，绝不挂定时清理。**
- 只有用户明确说"删除/清理"时：
  1. 先 `plan`，把带编号的候选表贴给用户
  2. 等用户回复编号或"全删过程文件"
  3. 再 `remove --pick <编号> --yes`
  4. 用户要彻底释放空间时才 `purge --yes`
- 全局环境（anaconda、运行时 Python、sandbox_envs）、连接器运行时、技能目录、会话痕迹永不删除，只能统计。
- 全局 pip/npm 缓存走独立入口：`gplan` → `gclean --pick N --yes`，不得混进任务候选表。
```

## 各平台落地位置

| 平台 | 放入位置 | 触发方式 |
|---|---|---|
| 豆包工作 / 其它支持 SKILL.md 的 Agent | Agent 的技能目录（如 `<agent_home>/skills/task-cleaner/`） | 元数据匹配（用户提到清理/产物/回收站等） |
| WorkBuddy | 技能目录（"技能与智能体"设置里可见） | 同 SKILL.md 形态；**不要**用它的"任务保留期限"代替本技能（那只清对话记录） |
| DSH | 全局 `~/.dsh/AGENTS.md` + 项目级 `AGENTS.md` | 每会话自动加载 |
| Codex | 项目根 `AGENTS.md` | 自动加载 |
| Cursor | 项目根 `.cursorrules` | 自动加载 |
| Claude Code | 项目根 `CLAUDE.md` | 自动加载 |

## 与平台原生清理的关系

| 平台 | 原生行为 | 本技能的补充 |
|---|---|---|
| WorkBuddy | 删任务可勾选"连带删除文件"；保留期只清对话记录 | 提供**编号勾选 + 30 天回收站 + 还原** |
| DSH | 删工作区只解除注册，删会话只归档 | 提供**真删但可还原、可审计**的路径（不替换其默认保守策略） |
| 豆包工作 | 不自动清理任何产物 | 提供登记与按指令清理 |
| Codex/Claude 等 | 无清理概念 | 提供同一套约定 |

## 安装与自检

```bash
# 1. 放进技能目录（或任意位置，纯标准库无需安装）
# 2. 自检
python scripts/test_registry.py
# 3. 在项目里初始化
python scripts/registry.py init --root <项目根>
python scripts/registry.py status --root <项目根>
```

- Python 3.8+，无第三方依赖；Windows / macOS / Linux 通用。
- 若某环境只有一个 3.7 的解释器（如老版本 anaconda 环境），改用其他 3.8+ 解释器，或在项目里建 venv 后调用。
