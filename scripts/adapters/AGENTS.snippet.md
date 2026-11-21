## 文件登记与清理（task-cleaner）

- 你产出的文件，用一个命令登记，不要移动它们：
  `python <skill>/scripts/registry.py register --path <路径> --kind <artifact|script|data|temp|dependency|cache|log|config> --task <任务id>`
- **绝不在任务结束时自行清理，绝不挂定时清理。**
- 只有用户明确说"删除/清理"时：先 `plan` 并把带编号的候选表贴给用户 → 等用户勾选 → 再 `remove --pick <编号> --yes` → 用户要彻底释放空间时才 `purge --yes`。
- 全局环境（anaconda、运行时 Python、sandbox_envs）、连接器运行时、技能目录、会话痕迹永不删除，只能统计。
- 全局 pip/npm 缓存走独立入口：`gplan` → `gclean --pick N --yes`，不得混进任务候选表。
