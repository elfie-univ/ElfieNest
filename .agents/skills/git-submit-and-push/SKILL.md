---
name: git-submit-and-push
description: 使用 Git 和 gh 稳定完成 ElfieNest 功能分支推送、Pull Request、原生 merge queue 与远端结果核验，并在认证、网络或 worktree 权限出错时做有界恢复。仅在用户明确要求远端 GitHub 写入或出现相关故障时使用；本地 commit 与质量检查选择遵循仓库现有规则。
---

# GitHub 交付与故障恢复

## 边界与事实源

- 本技能只管理远端 GitHub 交付和故障恢复，不决定跑哪些质量检查。验证范围和命令只以根/目录 `AGENTS.md`、`CONTRIBUTING.md`、`scripts/pre_submit_gate.sh`、机器分类器和 CI 为准。
- “本地提交”或 `commit` 只创建本地 commit；“推送”只更新功能分支；明确的“提交代码到主线”“交付”或“合并到远程主分支”才进入功能分支、PR 和 merge queue 流程。
- 用户已明确授权当前任务的远端交付时，该授权覆盖正常重试、PR 创建或复用、入队和结果核验，不重复询问内部步骤。
- Git 负责仓库传输，`gh` 负责 GitHub API；其中一个成功不能证明另一个可用。

## 出错后诊断

健康的远端操作不预跑探测。出现认证、DNS、TLS、连接关闭、沙箱或 worktree 权限错误后运行：

```bash
bash .agents/skills/git-submit-and-push/scripts/github_access_preflight.sh
```

- 脚本只输出工具路径、协议、环境覆盖变量名、凭据可取性、API 身份和远端 main SHA，永不输出 token。
- 普通沙箱出现 `Operation not permitted`、凭据不可取或 worktree lock 错误时，用最小宿主权限原样重跑失败命令或探测一次；这不是用户退出登录。
- 宿主 `gh auth token` 可取且 `gh api user --jq .login` 成功即证明 `gh` 认证有效。若清除 `GH_TOKEN`、`GITHUB_TOKEN` 或 `GH_CONFIG_DIR` 等覆盖后恢复，则修正启动环境，不要求用户退出有效账号。
- 只有宿主仍取不到凭据或 API 明确返回 401/`Bad credentials`，才运行一次 `gh auth login --hostname github.com --git-protocol ssh --web` 并用 `gh api user` 复核。
- 日常交付只使用 Git 与 `gh`；浏览器只用于 `gh auth login` 发起的交互，不复制 token，也不把浏览器当作 GitHub 操作通道。

## 有上限的恢复

| 失败类型 | 处理 |
| --- | --- |
| 只读 Git/gh 操作出现 DNS、TLS、连接关闭或 timeout | 最多重试 2 次，短退避 2 秒、5 秒 |
| `push`、创建 PR 或入队的结果不确定 | 先查询远端 ref、现有 PR 或 `mergeQueueEntry`；确认未生效后只重试 1 次 |
| 401、`Bad credentials` 或宿主 keyring 不可取 | 不做网络重试；按诊断流程执行一次交互恢复 |
| worktree lock 或沙箱权限错误 | 用最小宿主权限原样重试 1 次；不 reset、不换协议、不改代码 |
| SSH push 达到上限但宿主 `gh api user` 有效 | 确认远端未写入，临时使用 `gh auth git-credential` 做一次 HTTPS 读取；成功后只允许一次同配置的明确分支 push |

任何失败都不得使用 force push、`--admin`、`--no-verify`、删除远端引用、修改保护规则或无上限循环。

## 功能分支 push

先按仓库当前权威规则完成远端写入所需验证。确认当前分支不是 `main`，使用明确 refspec：

```bash
git push -u origin HEAD:refs/heads/<功能分支>
```

结果不确定时，用 `git ls-remote origin refs/heads/<功能分支>` 比较候选 SHA；相等即成功，远端未生效才按上限重试。临时 HTTPS fallback 不得修改 `origin` 或全局 Git 配置；失败后结束当前写入周期。

## PR 与原生 merge queue

1. 按 head 分支查询现有 PR；创建结果不确定时先查询，确认不存在才重试一次。
2. 核对远端 PR head 等于候选 SHA。main 仅向前移动不触发 rebase、合并 main 或重跑；只有候选变化或真实冲突才产生新候选。
3. 等待该 SHA 必需的 `elfienest/merge-gate`。内部 `elfienest/ci-gate` 只用于诊断失败，不额外形成第二个交付等待条件。
4. 绑定候选 head 使用原生入口：

   ```bash
   gh pr merge <PR> --repo <owner>/<repo> --match-head-commit <候选 SHA>
   ```

5. 若活动 ruleset 已确认要求 merge queue，而 CLI 在门禁全绿后仍误报 `Auto merge is not allowed`，先确认 `mergeQueueEntry` 为空，再用 `gh api graphql` 调用原生 `enqueuePullRequest` 并绑定 `expectedHeadOid`；不启用 auto-merge，不使用 `--admin`。调用超时后先查询条目，只有仍为空才重试一次。
6. 合并后确认 PR 状态为 `MERGED`、PR head 仍是候选 SHA，且 `merge_commit_sha` 等于或属于当前远端 main 的祖先；多人并发时不要求 main tip 等于本次 merge SHA，也不以本地 tracking ref 代替远端事实。

`GH013` 或主分支规则拒绝不是重试直接 push main 的理由，必须继续使用受保护的 PR/merge queue 流程。完整验证、发布和 CI 失败修复由仓库质量体系管理，不在本技能重复定义。
