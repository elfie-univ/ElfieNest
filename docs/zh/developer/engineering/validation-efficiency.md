# 测试门禁提效与运行历史审查

状态：当前实现快照，2026-08-20。

本文记录仓库已经具备的质量与测试提效措施、已验证证据，以及以后审查运行记录的
清单。它是稳定的工程指南，不替代 CI 日志，也不是自动生成的运行台账。

## 已经落地的能力

- **格式快线。** commit/push 门禁在测试前检查 diff 格式和范围内 Ruff 规则。
  `--fix-format` 只写本次范围内 dirty/untracked 的 Python 文件；同一文件同时有
  staged/unstaged 改动时停止，不覆盖内容。格式失败不会启动更大的测试门禁。
- **分级交付。** `commit` 使用 G1，功能分支 `push` 使用 G2，主线/发布、治理、
  工具链或未知影响使用 G3。`--no-cache` 不会改变所选级别。
- **范围化证据复用。** 确定性检查按不可变基础提交、候选输入、命令身份和本机工具链
  建 key。失败结果永远不会写成通过证据。G3 后盾包含仓库测试包和 25 个 App 模块包；
  每个模块由本地 Python 静态依赖闭包与显式动态/资源输入共同决定范围。
- **可移植 coverage。** coverage 片段统一为仓库相对路径，并校验可读性和元数据；包含
  不安全路径的片段会被拒绝。所有必要片段合并后只执行一次全局阈值检查。
- **提交权威入口。** Git 提交技能把标准 commit/push/main 流程接到
  `scripts/pre_submit_gate.sh`，远端操作只用终端 Git。pre-commit hook 仍是只检查的
  Gitleaks；裸 `git commit` 不能代替分级门禁。

## 验证快照

以下证据来自 2026-08-20 的第二阶段候选，证明机制有效，但不承诺每种改动都有固定的
提速比例。

| 证据 | 结果 |
| --- | --- |
| 本地最终 G3 | 通过；合并 coverage 79.32% |
| App setup 包，冷启动 → 热复用 | 3 个测试 4.11 秒 → 1.19 秒；第二次复用通过记录且未启动 pytest |
| App CLI 包，冷启动 → 热复用 | 188 个测试约 44.91 秒 → 2.51 秒；第二次复用通过记录 |
| 指纹输入范围 | 旧的单一 App 范围 1,570 个文件；当前 setup 328 个；当前 CLI 609 个 |
| 聚焦门禁/测试包回归 | coverage 路径修复后 61 项通过 |

本实现的提交为：`81a2a388`（第二阶段治理）和 `88732411`（实现及 coverage/CLI
修复）。

## 标准审查命令

使用受控入口，后续门禁才能复用结果：

```bash
git fetch --prune origin main
bash scripts/pre_submit_gate.sh --stage commit --fix-format \
  --base-sha "$(git rev-parse origin/main^{commit})"
```

要做单个测试包的直接实验，可在同一个缓存根连续跑两次并比较输出和 `real` 时间：

```bash
CACHE=$(mktemp -d /private/tmp/elfienest-validation.XXXXXX)
time .venv/bin/python3 scripts/architecture/validation_test_bundles.py \
  --selectors test/app/features/setup \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --cache-root "$CACHE"
time .venv/bin/python3 scripts/architecture/validation_test_bundles.py \
  --selectors test/app/features/setup \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --cache-root "$CACHE"
```

第一次应报告执行测试包；第二次应报告 `reused passed test bundle`，且不能启动 pytest。
裸 `pytest` 仍是诊断命令，不产生提交门禁可复用证据。

## 后续运行历史要看什么

每次比较最近运行时，先记录：

1. candidate SHA、不可变 base SHA、阶段和请求的 selector；
2. 实际执行包、复用包和每个包的 wall time；
3. 实际运行的格式、质量、测试、coverage 和文档命令；
4. 精确失败、重试次数，以及是否有失败结果被接受；
5. 工具链/平台和缓存根身份。

重点查四类重复或风险：

- 同一 key 在输入、工具链和 base 都未变化时重复执行；
- 仅格式失败后却启动完整 G3；
- 未变化的测试包因过宽输入或 Worktree 路径而失效；
- 失败结果被写入或读取成通过缓存。

发现问题时，先重现一条精确命令，再检查测试包输入闭包和 cache key。不要只凭一次热
缓存命中就宣称提速；必须在同一候选上比较冷启动和同 key 热复用。

## 证据边界与后续工作

- `build/validation-cache/` 是被忽略的本地证据，只能解释本地复用，不能替代新 commit
  SHA 的 CI 证据。
- 默认缓存根按 Worktree 分开。跨 Worktree 复用需要显式设置共享的
  `ELFIENEST_VALIDATION_CACHE_ROOT`；自动统一缓存根尚未实现。
- 当前远端 CI 在候选推送时仍运行完整 Python 测试命令，远端按测试包复用产物尚未接入。
- 当前缓存记录还不是持久、集中化的耗时历史；仓库也不能自动摄取未来所有 Codex 聊天
  transcript。后续监控应输出小型结构化 JSONL 运行摘要（candidate/base、选择/复用包、
  时长、失败和重试原因），并作为本地或 CI 产物保留。

以后要求审查最近门禁历史时，以本文为清单，再读取提供的命令输出、缓存记录和 CI 产物，
分别报告：已验证复用、无效重复、失效原因、环境阻塞和下一项最小优化。
