---
name: git-submit-and-push
description: 使用 Git 和 gh 稳定完成 ElfieNest 当前功能分支的显式 push 与远端 SHA 核验，并在认证、DNS、TLS 或 worktree 权限出错时做有界恢复。仅在用户当前指令明确要求 push 功能分支或相关 Git/GitHub 故障已经出现时使用；不创建 Pull Request、不操作 main 或 merge queue。
---

# 功能分支 Push 与 GitHub 访问恢复

## 严格边界

- 本技能只执行用户当前消息明确授权的功能分支 push；不决定本地验证范围，不替代根/目录 `AGENTS.md`、`CONTRIBUTING.md`、机器分类器或 CI。
- “开始实现”“按计划执行”“commit”“完成”或“交付”都不触发本技能。计划、技能、旧任务和历史授权不能产生 push 权限。
- push 授权只绑定当前任务、仓库和功能分支；它不创建 Pull Request、不更新 main、不等待或操作 merge queue。
- 同一 SHA 的一次有界恢复属于同一个已授权 push；分支、仓库、任务或候选 SHA 变化时停止并重新取得对应动作指令。
- Git 负责仓库传输，`gh` 负责 GitHub API；其中一个成功不能证明另一个可用。

## 出错后诊断

健康操作不预跑探测。出现认证、DNS、TLS、连接关闭、沙箱或 worktree 权限错误后运行：

```bash
bash .agents/skills/git-submit-and-push/scripts/github_access_preflight.sh
```

- 脚本只输出工具路径、协议、环境覆盖变量名、凭据可取性、API 身份和远端 main SHA，永不输出 token。
- 普通沙箱出现 `Operation not permitted`、凭据不可取或 worktree lock 错误时，用最小宿主权限原样重跑失败命令或探测一次；这不是用户退出登录。
- 宿主 `gh auth token` 可取且 `gh api user --jq .login` 成功即证明 `gh` 认证有效。若清除 `GH_TOKEN`、`GITHUB_TOKEN` 或 `GH_CONFIG_DIR` 等覆盖后恢复，则修正启动环境，不要求用户退出有效账号。
- 只有宿主仍取不到凭据或 API 明确返回 401/`Bad credentials`，才运行一次 `gh auth login --hostname github.com --git-protocol ssh --web` 并用 `gh api user` 复核。
- 日常操作只使用 Git 与 `gh`；浏览器只用于 `gh auth login` 发起的交互，不复制 token，也不把浏览器当作 GitHub 操作通道。

## 有上限的恢复

| 失败类型 | 处理 |
| --- | --- |
| 只读 Git/gh 操作出现 DNS、TLS、连接关闭或 timeout | 最多重试 2 次，短退避 2 秒、5 秒 |
| push 结果不确定 | 先查询精确远端分支 ref；确认未生效后只重试 1 次 |
| 401、`Bad credentials` 或宿主 keyring 不可取 | 不做网络重试；按诊断流程执行一次交互恢复 |
| worktree lock 或沙箱权限错误 | 用最小宿主权限原样重试 1 次；不 reset、不换协议、不改代码 |
| SSH push 达到上限但宿主 `gh api user` 有效 | 确认远端未写入，临时使用 `gh auth git-credential` 做一次 HTTPS 读取；成功后只允许一次同配置的明确分支 push |

任何失败都不得使用 force push、`--admin`、`--no-verify`、删除远端引用、修改保护规则或无上限循环。

## 功能分支 Push

1. 按仓库权威规则完成当前 push 所需的最小验证，确认工作区与目标路径没有混入无关改动。
2. 确认当前分支既不是 `main`，也不是 merge queue 的只读 ref；冻结当前候选 SHA。
3. 使用明确 refspec：

   ```bash
   git push -u origin HEAD:refs/heads/<功能分支>
   ```

4. 结果不确定时，用 `git ls-remote origin refs/heads/<功能分支>` 比较候选 SHA；相等即成功，远端未生效才按上限重试。
5. 临时 HTTPS fallback 不得修改 `origin` 或全局 Git 配置；失败后结束本次写入周期并报告。
6. 远端分支 SHA 核验成功后停止。不得因为分支已 push、任务完成、main 前进或分支存在较久而进入任何 PR 或主线动作。

主分支规则拒绝不是重试直接写 main 的理由。用户以后明确要求创建 PR 或合并 main 时，另行使用仓库的窄主线技能。
