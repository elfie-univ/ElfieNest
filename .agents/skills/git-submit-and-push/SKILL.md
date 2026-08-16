---
name: git-submit-and-push
description: 评估已完成改动的提交时机，并完成 Git 提交和远端推送，包含工作区审查、测试、敏感信息检查、暂存、提交、推送和远端状态验证。完成一组已验证改动、用户确认界面验收，或用户说“提交”“提交代码”“commit 一下”“保存到 Git”及要求团队共享时必须使用；除非用户明确要求只保留本地提交，否则提交默认包含 push。
---

# Git 提交并推送

把“提交”视为完整的远端交付流程，而不是仅创建本地 commit。推送成功并验证远端分支后才算完成。

## 强制规则

1. 用户说“提交”时默认执行 `commit + push`。只有用户明确说“只提交本地”“不要推送”时才能停在本地。
2. 每次完成并验证一组改动后，主动评估是否已形成边界清晰、没有已知问题的提交节点。符合时自动 `commit + push`，不等待用户再次要求提交。
3. 不提交仍在调试、测试失败、存在已知 bug 或尚待确认的半成品。对于需要用户目视验收的界面改动，用户说“没 bug 了”“可以了”或“验收通过”即视为提交和推送确认。
4. 提交前运行 `git status --short --branch`，确认当前分支、远端跟踪关系和所有改动来源。
5. 不覆盖或回退用户已有改动。用户要求提交“当前代码”时包含当前工作区全部目标改动；范围不明确时根据当前任务边界审慎选择。
6. 暂存或提交前必须先同步远端基础提交并运行仓库硬门禁：
   `git fetch --prune origin main`，然后执行
   `bash scripts/pre_submit_gate.sh --base-sha "$(git rev-parse origin/main^{commit})"`。
   门禁会把未暂存改动放入临时候选树，运行不可变基础分支架构 ratchet、锁文件与工具链、
   质量基线、pre-commit/Gitleaks、完整 pytest 和文档构建；门禁失败或环境预检未通过时
   不得提交、推送或合并。聚焦测试通过不能替代这一步。
7. 检查暂存内容，禁止提交本地密钥、Token、密码、运行时配置或被 `.gitignore` 保护的敏感文件。
8. 禁止使用 `--no-verify` 绕过 pre-commit。钩子失败时修复问题并重新提交。
9. 创建 commit 后立即推送当前分支。已有上游时运行 `git push`；没有上游时运行 `git push -u origin <branch>`。
10. 推送失败不算完成。继续处理可恢复的网络、认证、非快进或分支跟踪问题；无法恢复时明确报告 commit 仅存在本地。
11. 推送后再次运行 `git status --short --branch`，确认 ahead 计数清零，并报告 commit、分支和远端。
12. 在 worktree 中完成并经用户确认的功能，还要遵循仓库 `AGENTS.md` 的推送和主分支同步流程。

## 标准流程

### 1. 审查与验证

```bash
git status --short --branch
git diff --check
git diff --stat

git fetch --prune origin main
bash scripts/pre_submit_gate.sh \
  --base-sha "$(git rev-parse origin/main^{commit})"
```

读取关键差异并运行相关测试。硬门禁会审查当前工作树（包括未暂存文件）；若本地落后
远端，先安全拉取并处理冲突，不丢弃工作区内容。门禁的环境预检若返回阻塞状态，必须
换到允许回环端口的宿主或提升权限环境重新运行同一门禁，不得删测试、跳过全量套件或
把失败改成警告。

### 2. 暂存与提交

```bash
git add <目标文件>
git diff --cached --check
git diff --cached --stat
git commit -m "<符合项目约定的消息>"
```

提交消息应准确概括行为变化。多个独立主题可以拆分成多个 commit，但所有目标 commit 都必须推送。

### 3. 推送与确认

```bash
git push
git status --short --branch
git log -1 --oneline --decorate
```

没有上游分支时使用：

```bash
git push -u origin <当前分支>
```

最终报告必须包含：提交哈希、当前分支、推送目标、推送结果、测试结果，以及是否仍有未提交改动。
