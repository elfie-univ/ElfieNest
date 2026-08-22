---
name: git-submit-and-push
description: 管理 Git 的本地 commit、功能分支推送和主线合并。用户说 commit 时只创建本地提交；只有明确说 push/推送才执行远端写入；主线合并或发布才运行完整门禁。
---

# Git 提交、推送与合并

把本地 `commit`、远端 `push` 和主线 `merge` 视为三个独立动作，绝不从其中一个推断另外两个。

## 术语路由

- `commit`：只创建本地 Git commit；不 fetch、不 push、不合并主分支。
- `push` / “推送”：用户明确要求远端更新时，执行功能分支推送流程。
- “合并到远程主分支” / “发布”：执行主线合并或发布流程。
- 仅说“提交”时，不把它自动扩展成 push；只有用户明确说“推送”才写远端。

## 按风险选择门禁

- **S 级本地 commit**：单个子系统内的局部改动，不改变公开 API、持久化契约、架构边界或生命周期所有权。只做直接相关检查；CSS-only 改动不启动服务、Godot、浏览器或全套测试。
- **M/L 级本地 commit**，或用户明确要求“完整门禁”：运行 `scripts/pre_submit_gate.sh --stage commit`。
- **功能分支 push**：运行 `scripts/pre_submit_gate.sh --stage push`，然后推送当前功能分支。
- **主线合并/发布**：运行 `scripts/pre_submit_gate.sh --stage main`，并完成主线状态核验。

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

推送后再次运行 `git status --short --branch`，确认当前分支没有未推送的 ahead commit。禁止 `--force`、`--force-with-lease`、删除远程引用或擅自改走 PR。

## 主线合并或发布时

只有用户明确要求“合并到远程主分支”或“发布”时，才同步 `origin/main`、运行 main 级门禁，并在确认目标 commit 是 `origin/main` 的祖先后执行非强制快进更新。主线合并完成后核验远程主分支、本地 main worktree 和任务 worktree 状态。

## 安全边界

- 不覆盖或回退用户已有改动，不自动 stash、reset、checkout 或清理无关 worktree。
- 暂存前检查所有目标路径，禁止提交密钥、Token、密码、运行时配置、用户数据或生成物。
- “commit”不会授权远端写操作；“push”不会授权主线合并；“合并主分支”才授权主线写入。
