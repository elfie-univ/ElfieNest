---
name: git-submit-and-push
description: 管理 Git 的本地 commit、功能分支推送、Pull Request 合并队列和发布。用户说 commit 时只创建本地提交；只有明确说 push/推送才执行远端写入；普通主线合并依赖精确候选 CI 与 merge queue，完整门禁只用于合并后健康和发布。
---

# Git 提交、推送与合并

把本地 `commit`、远端 `push` 和主线 `merge` 视为三个独立动作，绝不从其中一个推断另外两个。

## 术语路由

- `commit`：只创建本地 Git commit；不 fetch、不 push、不合并主分支。
- `push` / “推送”：用户明确要求远端更新时，执行功能分支推送流程。
- “合并到远程主分支”：推送功能分支、等待精确候选 CI，并进入 merge queue；不直接 Push main。
- “发布”：在已接受的精确 SHA 上追加完整 G3 与发布验收。
- 仅说“提交”时，不把它自动扩展成 push；只有用户明确说“推送”才写远端。

## 按风险选择门禁

- **S 级本地 commit**：单个子系统内的局部改动，不改变公开 API、持久化契约、架构边界或生命周期所有权。只做直接相关检查；CSS-only 改动不启动服务、Godot、浏览器或全套测试。
- **M/L 级本地 commit**，或用户明确要求“完整门禁”：运行 `scripts/pre_submit_gate.sh --stage commit`。
- **功能分支 push**：运行 `scripts/pre_submit_gate.sh --stage push`，然后推送当前功能分支。
- **普通主线合并**：不运行本地全仓门禁；要求精确 PR head 的 `elfienest/ci-gate` 及其必需包装 `elfienest/merge-gate` 通过，再进入 merge queue 并等待同名合并门复检合成提交。
- **发布或显式完整验证**：运行 `scripts/pre_submit_gate.sh --stage full`，并完成发布状态核验。

门禁失败必须区分代码失败、环境阻塞和远端拒绝；不得用 `--no-verify`、删除扫描器或放宽检查消除失败。

## S 级本地 commit 快速路径

1. 运行 `git status --short --branch`，确认当前分支并识别无关改动；无关文件不得顺手提交。
2. 阅读目标 diff，运行 `git diff --check` 和与改动直接相关的最小验证。已有同一源码状态的有效证据可以复用，不重复启动无关服务或全套测试。
3. 只暂存用户目标范围内的文件：

   ```bash
   git add <目标文件>
   git diff --cached --check
   git diff --cached --stat
   ```

4. 对暂存内容执行仓库已有的定向敏感信息检查；不要为了本地 S 级 commit 运行 `pre-commit run --all-files`。
5. 创建本地 commit：

   ```bash
   git commit -m "<准确概括改动的提交消息>"
   ```

6. 提交后运行 `git status --short --branch` 和 `git log -1 --oneline --decorate`，报告 commit、分支和剩余改动；到此停止，不 push。

## 明确要求 push 时

用户明确说“推送”或“commit 并 push”后，先确保目标 commit 已通过对应验证，再使用明确的功能分支 refspec：

```bash
git push -u origin HEAD:refs/heads/<当前功能分支>
```

推送后再次运行 `git status --short --branch`，确认当前分支没有未推送的 ahead commit。禁止 `--force`、`--force-with-lease`、删除远程引用或绕过 Pull Request。

## 主线合并或发布时

只有用户明确要求“合并到远程主分支”时，才把已经推送的精确候选送入 Pull Request 合并流程：

1. 核对远端 PR head SHA 与已验证 SHA 一致，并等待 `elfienest/ci-gate` 及候选阶段的 `elfienest/merge-gate`；
2. main 仅向前移动不是重跑理由，不把最新 main 合回候选，也不持续 rebase；
3. 真实冲突或候选 commit 变化时才产生新 SHA 并重跑受影响证据；
4. 进入 GitHub merge queue，等待同名 `elfienest/merge-gate` 对合成提交做秒级复检，由 GitHub 串行化最终写入；
5. 合并后核验远端 main 包含该候选，并记录异步完整后盾状态。最新 main 完整后盾为红时，只允许受审计的聚焦恢复或回滚。

只有“发布”或用户明确要求完整验证时才在目标 SHA 上运行 `--stage full`。不得用直接 main Push、反复合并移动主线或本地全仓重跑代替 merge queue。

## 安全边界

- 不覆盖或回退用户已有改动，不自动 stash、reset、checkout 或清理无关 worktree。
- 暂存前检查所有目标路径，禁止提交密钥、Token、密码、运行时配置、用户数据或生成物。
- “commit”不会授权远端写操作；“push”不会授权主线合并；“合并主分支”授权进入受保护的 PR/merge queue，不授权绕过规则直接 Push main。
