---
name: git-submit-and-push
description: 管理 ElfieNest 的本地 commit、功能分支 push、Git/gh 认证与网络故障诊断、Pull Request、原生 merge queue 和发布。用户要求提交、推送、合并主线，或 Codex 遇到 GitHub keyring、TLS、DNS、worktree 权限及受保护 main 错误时使用；严格区分本地与远端授权。
---

# Git 提交、推送与队列合并

把本地 `commit`、远端 `push` 和主线 `merge` 视为三个独立动作，绝不从其中一个推断另外两个。Git 负责仓库传输，`gh` 负责 GitHub API；其中一个成功不能证明另一个可用。

## 动作与授权

- `commit`：只创建本地 Git commit；不 fetch、不 push、不合并主分支。
- `push` / “推送”：用户明确要求远端更新时，验证并推送当前功能分支。
- “合并到远程主分支”：推送功能分支、创建或复用 PR、等待精确候选 CI，并进入 merge queue；不直接 push main。
- “发布”：在已接受的精确 SHA 上追加完整 G3 与发布验收。
- 用户对当前任务的 push 或主线合并授权持续覆盖正常重试、PR 和队列核验；不得把内部步骤再次变成确认问题。

## 按实际影响选择验证

- 局部本地 commit：运行 `git diff --check`、直接相关测试及现成快速的局部 lint/typecheck。CSS-only 等局部改动不启动服务、Godot、浏览器或全套测试。
- 涉及 schema、公开 API、持久化、架构边界或生命周期所有权的本地 checkpoint：运行 `scripts/pre_submit_gate.sh --stage commit`。
- 功能分支 push：运行 `scripts/pre_submit_gate.sh --stage push`，然后推送当前功能分支。
- 普通主线合并：不运行本地全仓门禁；只认精确 PR head 的 `elfienest/ci-gate` 和候选 `elfienest/merge-gate`，再进入 merge queue。
- 发布或用户显式完整验证：运行 `scripts/pre_submit_gate.sh --stage full` 并核验发布状态。

不使用主观大小标签。治理、工具链、锁文件和未知影响由远端可信影响面分类器 fail-closed 选择 Lane。门禁失败必须区分代码失败、环境阻塞和远端拒绝；不得用 `--no-verify`、删除扫描器或放宽检查消除失败。

## 远端操作前置探测

首次远端操作前，或出现认证、网络、权限错误后，在当前 Codex 执行环境运行：

```bash
bash .agents/skills/git-submit-and-push/scripts/github_access_preflight.sh
```

脚本只输出 Git/gh 路径、协议、环境覆盖变量名、凭据可取性、API 身份和远端 main SHA，永不输出 token。按以下顺序处理：

1. 普通沙箱出现 `Operation not permitted`、`no oauth token found`、本地端口/进程受限，或 worktree 的 `index.lock`、`ORIG_HEAD.lock`、`FETCH_HEAD` 无法创建时，先用最小宿主权限重跑原命令或前置探测一次；这不是用户退出登录。
2. 若宿主环境能执行 `gh auth token` 且 `gh api user --jq .login` 返回账号，认证有效。`gh auth status` 的 timeout 或笼统 invalid 提示不能推翻这两个直接证据。
3. 若探测报告 `GH_TOKEN`、`GITHUB_TOKEN`、企业版 token 或 `GH_CONFIG_DIR` 覆盖，只报告变量名，不读取或打印值。用清除 token 覆盖的命令复核 keyring：

   ```bash
   env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN -u GITHUB_ENTERPRISE_TOKEN -u GH_CONFIG_DIR gh auth token --hostname github.com >/dev/null
   env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN -u GITHUB_ENTERPRISE_TOKEN -u GH_CONFIG_DIR gh api user --jq .login
   ```

   清除覆盖后成功即为 Codex 环境覆盖冲突；从 Codex 启动环境移除无效变量并重启任务，不要求用户退出有效账号。
4. 只有宿主环境仍取不到凭据或 API 明确返回 401/Bad credentials，才运行交互恢复：

   ```bash
   gh auth login --hostname github.com --git-protocol ssh --web
   gh auth switch --hostname github.com --user <账号>
   gh api user --jq .login
   ```

   说明登录原因并让用户完成 `gh` 打开的 device/browser 流程。日常 GitHub 交付只使用 Git 和 `gh`；不改用浏览器、`curl` 或复制 token。HTTPS Git 才需要 `gh auth setup-git`，SSH Git 不需要。

## 有上限的失败恢复

| 失败类型 | 处理 |
| --- | --- |
| `fetch`、`ls-remote`、PR/检查状态等只读操作出现 DNS、TLS、连接关闭或 timeout | 初次失败后最多重试 2 次，短退避 2 秒、5 秒；仍失败即报告 GitHub/网络阻塞 |
| `push`、创建 PR、入队等写操作 timeout 或连接中断 | 绝不盲目重发；先查询远端 ref、现有 PR 或 `mergeQueueEntry`。确认未生效后只重试 1 次 |
| SSH push 达到重试上限，但宿主 `gh api user` 有效 | 确认远端未写入，先用 Git HTTPS + `gh auth git-credential` 做一次只读 `ls-remote`；成功后允许一次临时 HTTPS push，不改 remote 或全局配置 |
| 401、Bad credentials、宿主 keyring 不可取 | 不做网络重试；按前置探测和一次交互登录恢复 |
| `GH013`、required check、PR 或 merge queue 规则拒绝 | 不重试直接 push main；改走功能分支、PR、精确检查和队列 |
| worktree lock 或沙箱 `Operation not permitted` | 申请最小宿主权限并原样重试 1 次；不 reset、不换协议、不改代码 |
| CI 代码失败 | 先诊断精确失败项；只有偶发/环境证据充分时重跑该失败 job 1 次，不重启全图 |

任何失败都禁止 force push、`--admin`、`--no-verify`、删除远端引用、改保护规则或循环等待无上限。

## 本地 commit

1. 运行 `git status --short --branch`，识别目标改动和无关改动。
2. 阅读目标 diff，运行已选最小验证；同一源码状态的有效证据直接复用。
3. 只暂存目标路径，运行 `git diff --cached --check`、`git diff --cached --stat` 和仓库已有的定向敏感信息检查；不要对局部提交自动运行 `pre-commit run --all-files`。
4. 运行 `git commit -m "<准确消息>"`。
5. 运行 `git status --short --branch` 和 `git log -1 --oneline --decorate`，报告 commit 与剩余改动；到此停止，不 push。

## 功能分支 push

确保当前分支不是 `main`，并使用明确 refspec：

```bash
git push -u origin HEAD:refs/heads/<功能分支>
```

若结果不确定，先运行 `git ls-remote origin refs/heads/<功能分支>`；远端 SHA 已等于候选即视为成功，未生效才重试一次。推送后比较本地候选和远端 SHA，并确认没有未推送的目标 commit。

若 SSH push 在允许的重试后仍只出现连接关闭或 TLS/DNS 故障，而宿主 `gh api user --jq .login` 有效，确认远端 ref 仍不存在，再先测试一次临时 HTTPS 读取：

```bash
GIT_TERMINAL_PROMPT=0 git \
  -c credential.helper= \
  -c credential.helper='!gh auth git-credential' \
  ls-remote https://github.com/<owner>/<repo>.git refs/heads/main
```

读取成功后，允许用同一临时配置 push 一次明确功能分支 refspec。该 fallback 不修改 `origin` 或全局 Git 配置；失败后结束当前写入周期，不继续切换协议或立即重试。若用户已要求持续完成交付，只有稍后的 Git/gh 只读健康探测恢复、且远端 ref 仍不存在时，才允许最多一个恢复写入周期；再次失败即报告网络阻塞。

## PR 与原生 merge queue

1. 创建 PR 前先按 head 分支查询 open/all PR，避免重复创建。创建命令 timeout 后先用 `gh pr list` 或 `gh api repos/<owner>/<repo>/pulls?...` 查询，确认不存在才重试一次。
2. 核对远端 PR head SHA 与已验证 SHA 一致，等待该 SHA 的 `elfienest/ci-gate` 和候选 `elfienest/merge-gate`。main 仅向前移动不是重跑理由；只有真实冲突或候选变化才产生新 SHA。
3. 优先使用 CLI 原生入口，并绑定 head：

   ```bash
   gh pr merge <PR> --repo <owner>/<repo> --match-head-commit <候选 SHA>
   ```

4. 若活动 ruleset 已确认要求 merge queue，但上述命令错误地返回 `Auto merge is not allowed for this repository`，不得开启仓库 auto-merge 或使用 `--admin`。先用 `gh pr view <PR> --json id,headRefOid,mergeStateStatus,mergeable` 取得 GraphQL ID 并确认 PR 可合并，再确认候选门禁全绿且 `mergeQueueEntry` 为空。然后用 `gh` 调用 GitHub 原生队列 mutation，并绑定 `expectedHeadOid`：

   ```bash
   gh api graphql \
     -f query='mutation($id:ID!,$oid:GitObjectID!){enqueuePullRequest(input:{pullRequestId:$id,expectedHeadOid:$oid}){mergeQueueEntry{id position state}}}' \
     -f id='<PR GraphQL ID>' \
     -f oid='<候选 SHA>'
   ```

   mutation timeout 后先用只读 GraphQL 查询 `node(id: $id) { ... on PullRequest { mergeQueueEntry { id position state } } }`；条目已存在即成功，为空才重试一次。
5. 等待 `merge_group` 上同名 `elfienest/merge-gate` 的秒级复检。合并后用 `gh api` 核验 PR 的 `merge_commit_sha`，再用 `git ls-remote origin refs/heads/main` 核验远端 main；不以本地 tracking ref 代替远端事实。

完整 G3 只用于 main 合并后健康、发布或用户显式完整验证。不得用直接 main push、反复合并移动主线或本地全仓重跑代替 merge queue。

## 安全边界

- 不覆盖或回退用户已有改动，不自动 stash、reset、checkout 或清理无关 worktree。
- 暂存前检查所有目标路径，禁止提交密钥、Token、密码、运行时配置、用户数据或生成物。
- “commit”不授权远端写入；“push”不授权主线合并；“合并主分支”授权受保护的 PR/merge queue，不授权绕过规则。
