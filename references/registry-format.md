# 登记文件格式

## 文件对

| 文件 | 读者 | 说明 |
|---|---|---|
| `agent-registry.json` | 机器 | 唯一事实源，程序只读写它 |
| `agent-registry.md` | 人 | 每次保存 JSON 后自动重生成，**不要手改** |
| `agent-registry.log` | 人/审计 | 每行动作一行 JSONL（init/register/remove/restore/purge） |
| `agent-registry.plan.json` | 机器 | 最近一次 `plan` 的编号映射；`remove` 用它，改完登记即失效 |

## JSON 结构

```json
{
  "schema": "agent-registry/1",
  "type": "root | sub",
  "project_root": "/home/user/projects/demo",
  "updated_at": "2026-11-21T11:49:19+08:00",
  "tasks": [
    { "id": "t1", "title": "汽水脚本部署", "status": "done",
      "created_at": "..." }
  ],
  "entries": [
    { "id": "e46b7668f", "task": "t1", "path": "artifacts/report.md",
      "kind": "artifact", "size": 17, "files": 1,
      "mtime": "...", "protected": false, "shared": false,
      "note": "用户最终报告", "status": "ok",
      "registered_at": "...", "batch": "b-..." }
  ],
  "batches": [
    { "id": "b-20261121-114919-01", "created_at": "...",
      "expires_at": "...", "entries": ["e9d579d52"],
      "purged": false, "restored": false }
  ]
}
```

## 字段含义

| 字段 | 说明 |
|---|---|
| `path` | **相对项目根的 POSIX 风格路径**（`/` 分隔）。绝对路径会被拒绝 |
| `kind` | `artifact`/`script`/`data`/`temp`/`dependency`/`cache`/`log`/`config` |
| `size` / `files` | 登记时的体积与文件数（目录为递归合计，跳过符号链接与 `.git`/`node_modules` 等） |
| `protected` | true = 永不进候选（自动命中名单或 `--protected`） |
| `shared` | 同一路径被**不同任务**登记过 → true，候选表里按保护处理 |
| `status` | `ok`（在位）/`trashed`（在回收站）/`purged`（已终删） |
| `batch` | 条目所属回收批次 |
| `batches[].expires_at` | 建立时间 + 30 天，`purge` 只处理已过期批次（`--force` 或 `--older-than 0` 才提前） |

## 去重规则

- 以 `path` 为唯一键；重复登记复用同一条目并刷新 `size/files/mtime/status`。
- 条目 id 由 `sha1(相对路径)[:8]` 生成，路径不变则 id 稳定，便于跨轮引用。

## MD 生成规则

三张表：按任务汇总、明细（可点击路径用的是反引号包裹的相对路径）、回收站批次。数字列统一走 `human_size()`（B/KB/MB/GB/TB，一位小数）。

## 版本演进

`schema` 固定为 `agent-registry/1`。升级时新增字段必须可缺省，旧登记文件读取后自动补默认值；不兼容变更才升 `schema` 版本并拒绝旧文件。
