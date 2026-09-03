---
name: git-main-delivery
description: 仅在用户当前消息明确要求 ElfieNest 创建 Pull Request 或合并到远程 main 时使用。对已经稳定并获用户验收的精确候选，每次最多创建或复用一个 PR；创建 PR 模式随后停止，合并 main 模式才等待 CI、进入原生 merge queue 并核验远端结果。规则、队列或必需检查无法确认时 fail closed；单维护者阶段的已知审查限制按版本化契约处理。
---

# ElfieNest 单一 PR 主线交付

## 触发与消费边界

- 只有当前用户消息明确要求“创建 PR”或“合并 main / 合并到远程主分支”时使用。计划、ADR、技能、旧任务、孤立的“完成/交付”以及此前已消费的授权都不能触发本技能。
- 授权绑定当前任务、仓库、功能分支、动作与冻结候选 SHA。每次最多创建或复用一个 PR；成功、取消、目标/范围变化或候选 SHA 变化都会消费或终止授权。
- queue 产生的合成 SHA 不是候选 SHA 变化；main 正常前进也不让已通过的候选证据失效。真实冲突必须退出队列并停止，不能以反复 merge/rebase main 制造新候选。
- “创建 PR”模式只创建或复用一个 PR、核验其 head 后停止，不等待合并、不入队。“合并 main”模式才执行本技能的完整后续步骤。
- 技术上建议多个 PR 属于范围扩张。只有用户事先明确批准准确 PR 数量与边界后才能另行安排；本技能单次仍只处理一个 PR。
- ElfieNest 禁止直接 push main、`--admin`、force push、`--no-verify`、修改 ruleset 或自动放宽检查。
- 认证、DNS、TLS、沙箱或 worktree 故障复用功能分支技能的安全 preflight 与重试上限。任何 PR/queue 写入结果不确定时先查询远端事实，确认未生效后最多重试一次；不使用浏览器代替 Git/gh。

## 1. 冻结候选和人工放行

1. 读取当前仓库规则，确认功能完整、聚焦验证已通过、用户要求的目视/行为验收已经完成，且工作区没有未纳入候选的任务改动。
2. 记录交付开始时间、仓库、功能分支与 `git rev-parse HEAD`。确认远端功能分支 ref 精确等于该 SHA；当前明确的 create-PR 或 merge-main 动作包含发布这个冻结 SHA 所必需的一次功能分支 push，可复用功能分支技能，但不会授权其他分支或后续新 SHA。
3. 从这一刻起不得修改、commit、amend、rebase 或 push 新代码。任何候选 SHA 变化都会使本次 PR/合并授权和预验证证据失效；停止并报告新 SHA，等待新的明确主线指令。

## 2. 实时核对主分支硬规则

使用 `gh api` 读取仓库和所有作用于 `refs/heads/main` 的活动 ruleset，并计算叠加后的有效规则。必须同时确认：

- enforcement 为 active，main 要求 Pull Request 和 merge queue；
- required status checks 包含预期 GitHub Actions App 产生的 `elfienest/merge-gate`；
- 读取 Pull Request 的 `required_approving_review_count`、`required_reviewers` 和 Code Owner 审查配置。当前仓库处于只有一名维护者的阶段，版本化治理契约明确记录第二人审批硬门尚不可实现；该已知限制不阻塞治理/CI 候选，但必须在交付报告中保留，不能伪称已经获得独立审查；
- 禁止直接/强制写 main，队列和 required-check 来源身份可识别。

只看缓存响应或某一个 ruleset 不算确认。API 失败、字段未知、多条规则无法合成、队列未启用或必需检查来源不明时都视为“无法确认”：fail closed，停止且不创建第二条路径。不得通过直接 main 技能绕过。出现第二名具有写权限的已验证维护者后，必须先按治理契约启用治理/CI 路径审批硬门并更新本技能；单维护者例外不能继续沿用。

## 3. PR 前精确候选验证

“合并 main”模式在创建 PR 前，从受信任的 main Workflow 对冻结 SHA 触发一次 candidate dispatch。运行必须绑定 exact target SHA，并从 main ref 使用受信任 Workflow：

```bash
gh workflow run ci.yml --ref main -f mode=candidate -f target_sha=<候选 SHA>
```

有界查询本次 dispatch，确认它成功并发布与候选 SHA、基础治理指纹、Manifest 版本、候选工具链指纹和受信任 Workflow 身份完全匹配的 candidate evidence。结果不确定时先查运行与证据，确认不存在后最多重试触发一次。失败、取消、超时、缺失或陈旧证据永不复用。

唯一 Bootstrap 例外：若当前受保护 main 尚不存在 `candidate-evidence-v1` 协议，不运行一个注定无法发布证据的预验证；直接创建本次唯一 PR，让其按不可变基础分类器正常运行选中 Lane。协议进入 main 后该例外自动消失，不能作为以后跳过 PR 前验证的开关。

## 4. 创建或复用唯一 PR

1. 按 owner/repo 与 head 分支查询所有 open PR。若已有一个且 head SHA 等于冻结候选，复用；若多于一个、head 不同或目标不是 main，停止。
2. 没有 PR 时只创建一个：

   ```bash
   gh pr create --base main --head <功能分支> --title <标题> --body-file <正文文件>
   ```

3. 创建结果不确定时先重新查询，确认没有生效后最多重试一次。再次核验 PR head 等于冻结候选。
4. 若用户只授权“创建 PR”，到此停止；不得运行任何合并或队列命令。

## 5. 等待检查、审查并进入原生队列

1. PR 事件应通过可信 candidate evidence 做快速身份复核；证据缺失或失效时重新运行受影响 Lane，而不是伪造通过。等待该 SHA 的 `elfienest/merge-gate`。单维护者阶段如候选包含治理/CI 路径，明确报告“独立维护者审查未执行”的已知限制；出现第二名已验证维护者后，这类候选必须获得一名非作者维护者的有效批准。
2. 每次状态变化都重新核验 PR head 仍等于冻结候选。绑定 head 请求原生合并入口：

   ```bash
   gh pr merge <PR> --repo <owner>/<repo> --match-head-commit <候选 SHA>
   ```

3. 若活动 ruleset 已确认要求 merge queue，而 CLI 在全绿后仍误报 auto-merge 不可用，先确认 `mergeQueueEntry` 为空，再以 PR node ID 和 expected head 调用原生 `enqueuePullRequest`。调用结果不确定时先查询，条目仍为空才重试一次；不启用 auto-merge。

   ```bash
   gh api graphql -f query='mutation($id:ID!,$head:GitObjectID!){enqueuePullRequest(input:{pullRequestId:$id,expectedHeadOid:$head}){mergeQueueEntry{id}}}' -F id=<PR_NODE_ID> -F head=<候选_SHA>
   ```

4. 在队列中只观察，不因 main 前进拉取、rebase 或重跑产品套件。merge-group 门只做秒级身份、父提交、冲突和门禁版本检查。

## 6. 停止、失败与最终核验

- 用户中途说停止、取消或不要合并时，立即检查 `mergeQueueEntry`。若条目存在，调用 `dequeuePullRequest`，再确认条目为空；不要关闭 PR，除非用户另外明确要求。

  ```bash
  gh api graphql -f query='mutation($id:ID!){dequeuePullRequest(input:{pullRequestId:$id}){mergeQueueEntry{id}}}' -F id=<PR_NODE_ID>
  ```

- CI 失败先报告精确失败项。修复会产生新候选，因此旧候选的证据及冻结授权失效；不得
  在旧候选下继续改代码、更新 PR 或创建第二个 PR。若用户随后授权修复并再次推送，必须
  保留原“合并 main”目标，不得把功能分支 push 当作交付完成；新候选须重新冻结、验证，
  并按当前授权边界继续或明确报告主线下一步。
- 合并后确认 PR 状态为 `MERGED`、PR head 仍是冻结 SHA，且 merge commit 属于当前远端 main 的祖先。多人并发时不要求 main tip 等于本次 merge SHA。
- 报告从冻结候选获得用户放行到远端 main 核验完成的总耗时；不要按 PR 数量重置计时，也不要把 GitHub/Runner 故障伪造成达标。
