# 发布记录与后续维护

**线上仓库：<https://github.com/Reed-hms/task-cleaner>**

| 项目 | 状态 |
|---|---|
| 可见性 | Public |
| 默认分支 | `main` |
| 提交 | 2 个（`feat: initial release v1.0.0` / `docs: add publishing guide`） |
| 受控文件 | 15 个 |
| 提交作者 | `<username>@users.noreply.github.com`（noreply 身份，不含真实邮箱） |
| 许可证 | MIT |
| CI | `.github/workflows/tests.yml`（ubuntu/windows/macos × py3.8 / py3.12） |
| 本地仓库 | `<仓库目录>` |

## 本机推送方式：SSH over 443

`github.com:443` 在本机网络上时通时断（HTTPS 推送直接 `Connection was reset`），因此没有走 HTTPS，改用 GitHub 的 443 备用端口：

- 远端地址：`git@github.com:<owner>/task-cleaner.git`
- `~/.ssh/config` 里把 `github.com` 重定向到 `ssh.github.com:443`
- 认证使用一把专用 ed25519 密钥（标题形如 `task-cleaner (workspace)`，已加到账号 SSH keys）

`~/.ssh/config` 参考内容（`<key-name>` 换成你的私钥文件名）：

```
Host github.com
    HostName ssh.github.com
    Port 443
    User git
    IdentityFile ~/.ssh/<key-name>
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
```

注意：该文件必须是 **UTF-8 无 BOM**。带 BOM 时 Git 会报 `no argument after keyword "\357\273\277"` 并直接退出。

验证：

```powershell
ssh -T git@github.com        # 应返回 Hi <username>!
```

## 日常维护命令

```powershell
cd <仓库目录>
git status -sb
git log --format="%h %an <%ae> %s"

# 改完文档或代码后
git add -A
git commit -m "docs: ..."
git push

# 发版
git tag v1.0.0
git push origin v1.0.0
```

## 发布后建议做的事

1. 仓库 About 补一句话描述，加 topics：`ai-agent`、`automation`、`file-management`、`python`
2. Actions 确认首次运行跑绿
3. 在 Releases 里基于 `v1.0.0` 打一个 release，正文直接引用 `CHANGELOG.md`
4. 以后加示例放 `examples/`，**不要**提交任何 `agent-registry.json` 或 `.agent-trash/`（`.gitignore` 已挡）

## 常见问题

**推送超时 / `Connection was reset`**
先 `ssh -T git@github.com` 判断是认证问题还是网络问题。认证返回 `Hi <username>!` 就说明是网络波动，重试即可；`github.com` 网页打不开时推送仍可能正常，因为走的是 `ssh.github.com:443`。

**想撤掉这把密钥**
GitHub → Settings → SSH and GPG keys，删除标题为 `task-cleaner ...` 的那一条，并删除本机私钥文件。

**想换回 HTTPS**
`git remote set-url origin https://github.com/<owner>/task-cleaner.git`，认证交给 Git Credential Manager。但本机网络对 `github.com:443` 不稳定，可能反复失败。

**提交作者显示不对**
`git config user.name/user.email` 会覆盖全局身份。改完用 `git rebase --root --exec "git commit --amend --no-edit --reset-author"` 统一改写历史，再 `git push --force-with-lease`。
