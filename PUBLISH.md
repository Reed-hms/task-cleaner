# 发布到 GitHub · 操作单

仓库已经在本地准备好：`<仓库目录>`（分支 `main`，2 个提交，15 个文件）。

## 已完成的前置

| 项目 | 状态 |
|---|---|
| 脱敏扫描（用户名 / 邮箱 / 本地绝对路径 / 解释器目录 / 运行时目录 / 用户目录） | ✅ 零命中 |
| 测试 | ✅ 13/13 通过（在仓库目录内实跑） |
| 提交作者 | `task-cleaner <task-cleaner@users.noreply.github.com>`（占位身份，不含真实邮箱） |
| 许可证 | MIT |
| CI | `.github/workflows/tests.yml`（ubuntu/windows/macos × py3.8/3.12） |

## 方式 A：自己建空仓库，我负责推送（最快）

1. 浏览器打开 <https://github.com/new>
2. 仓库名填 `task-cleaner`，**不要**勾 README / .gitignore / license（本地已有）
3. 选 Public（要开源）→ Create repository
4. 回来告诉我仓库地址，我执行：

```powershell
cd <仓库目录>
git remote add origin https://github.com/<你的用户名>/task-cleaner.git
git push -u origin main
```

推送时 Git Credential Manager 会弹浏览器让你授权（本机 `credential.helper=manager`，已验证可用）。

## 方式 B：我用浏览器代建 + 推送

你只要确认「用 `task-cleaner` 作为公开仓库名」，我用浏览器打开 `github.com/new` 建仓，再执行推送；若浏览器没登录 GitHub，会弹窗让你登录。

## 方式 C：命令行一次到位（需装 gh）

```powershell
winget install --id GitHub.cli
gh auth login                       # 选 GitHub.com → HTTPS → 浏览器授权
cd <仓库目录>
gh repo create task-cleaner --public --source . --push \
  --description "Sidecar file registry for AI agents: record task outputs, delete only what the user picks"
```

## 想让提交显示你自己的 GitHub 账号

当前作者是占位身份。拿到用户名后执行（把 `<ID>` 换成 GitHub 数字 ID，在 Settings → Emails 里可见）：

```powershell
cd <仓库目录>
git config user.name "<你的用户名>"
git config user.email "<ID>+<你的用户名>@users.noreply.github.com"
git commit --amend --reset-author --no-edit
```

这样既显示账号，又不会把真实邮箱写进提交历史。

## 推送后建议顺手做的四件事

1. 仓库 About 填一句话描述 + 加上 topics：`ai-agent`、`automation`、`file-management`、`python`
2. 打标签发版：`git tag v1.0.0 && git push origin v1.0.0`，在 Releases 里点 "Draft a new release"
3. 确认 Actions 跑绿（首次推送会自动触发 `tests.yml`）
4. 若以后要加示例，新增 `examples/`，**不要**把任何 `agent-registry.json` 提交进去（`.gitignore` 已挡住）

## 发布前最后一次自检（可选）

```powershell
cd <仓库目录>
python scripts/test_registry.py -v
git log --format="%h %an <%ae> %s"
git ls-files | findstr /i "registry.json"    # 应为空，避免把运行数据提交上去
```
