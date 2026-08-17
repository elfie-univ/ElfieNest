# 测试与质量

## 全量门禁的环境预检

启动全仓 pytest 门禁前，先检查当前宿主是否能绑定回环端口：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_environment.py
```

预检不会跳过或降级任何测试，退出码含义如下：

- `0`：允许回环端口绑定，运行一次 `pytest test/`；
- `2`：沙箱或宿主策略拒绝 `127.0.0.1:0`，不要在当前环境运行全量测试，应使用宿主或
  提升权限的环境把同一条全量命令运行一次；
- `1`：预检出现未预期错误，先诊断再启动全量门禁。

网关重启测试仍然属于全量套件。权限拒绝是执行环境结果，不是排除该测试或在单测重试后
再次重跑整套测试的理由。

## 测试层级

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/<changed-module>/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
# 仅在上方预检返回 0 后运行。
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/
```

测试目录镜像源码目录。根 `test/` 不直接放测试文件；架构测试负责目录边界、旧包名、
反向依赖和工程配置契约。

## CI 与测试失败判因

红色检查是需要调查的证据，不是要求立刻修改最近一条断言的指令。在修改生产代码、
测试、CI、Scanner 或质量基线前，必须按以下顺序确认原因：

1. 记录具体 workflow job、命令、失败断言和第一段有效 traceback。邮件标题或红色汇总卡
   片本身不足以作为证据。
2. 阅读当前生效的契约、配置和相关测试；代码看起来反常时再检查历史，尤其关注 lazy
   import、fallback、Adapter、测试夹具和边界例外。先恢复原始动机，再决定删除还是替换
   行为。
3. 追踪真实的调用、数据和依赖流向及其事实源。动态 import、`python -m`、subprocess
   和 Scanner 目标都必须纳入；藏在 lazy import 后面的依赖仍然是真实依赖。
4. 修改前先分类：

   | 分类 | 必须采取的修复方式 |
   | --- | --- |
   | 实现回归 | 用回归测试固定原本应保留的行为，再做最小生产代码修复。 |
   | 测试夹具或预期过时 | 先确认当前契约；只更新描述已接受契约的夹具或预期，保留行为断言。 |
   | 契约迁移不完整或装配遗漏 | 在组合边界完成所有权和注入，不反转目标契约，也不添加隐藏 fallback。 |
   | CI、工具链或环境失败 | 复现环境条件；若仓库配置违反项目契约就修配置，否则单独报告，不能排除产品测试。 |
   | 原因未确认 | 先补齐证据，不得声称问题已经修复。 |

5. 增加或恢复正向行为测试；涉及必需依赖时，同时增加负向的 fail-fast 测试。绝不能为
   了变绿而删除测试、增加宽泛 skip/xfail、扩大质量基线、使用 `--no-verify`，或用空值/
   默认 fallback 替代真实结果。
6. 分层验证：先跑聚焦行为测试，再跑受影响的架构/Scanner 检查、质量和密钥门禁，最后
   跑与风险相称的更大范围测试。分别说明通过、未运行和受环境阻塞的检查；本地局部变绿
   不等于远程 CI 已变绿。

修复总结必须写明：问题分类、恢复出的设计动机、明确保留的行为、实际运行的证据以及
所有剩余风险。这样才能避免把测试失败盲目改成断言变化，或悄悄丢掉产品功能。

## 架构治理检查

```bash
uv run --no-sync python scripts/architecture/app_layer_scan.py \
  --project-root . --mode deny-all
uv run --no-sync python scripts/architecture/system_layer_scan.py \
  --project-root . --mode deny-all
uv run --no-sync pytest test/architecture/
```

App 和系统 Scanner 债务已经清零，两套永久 Scanner 均以 `deny-all` 模式运行，不再使用
旧债基线。未来获批迁移若需要临时精确基线，必须随切片持续缩减并在清零后删除。CI 还会
使用 Pull Request 基础提交中的规则检查候选生产代码，因此同一变更不能放松评判自己的
规则。详见[仓库架构治理契约](../contracts/repository-governance)。

## 质量门

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync python scripts/check_quality_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit uv run --no-sync pre-commit run --all-files
```

质量基线只容纳已经存在的诊断；新增 Ruff、格式或 MyPy 诊断必须修复，不通过扩大
忽略项或改写基线隐藏。

## 分级验证门禁

先同步远程 `main`，再按改动运行最小安全级别：

```bash
git fetch --prune origin main
bash scripts/pre_submit_gate.sh --stage commit \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --closure-file task-closure.json
# 功能分支推送：使用 --stage push
# 主线合并或发布：使用 --stage main
```

G1（`commit`）检查改动文件、受影响测试和 closure `progress`；G2（`push`）追加质量基线
以及受影响的 API、持久化、架构或文档集成检查；G3（`main`）运行下面的完整门禁，包括不可变
基础提交架构 ratchet、锁文件和工具链、pre-commit/Gitleaks、完整 pytest、CLI smoke 和文档
构建。未知可执行路径、治理、工具链和锁文件改动自动升级到 G3。成功的精确候选结果可从被
忽略的 `build/validation-cache/` 复用，但不能替代新 commit SHA 的 CI。

必需检查失败，或 G3 的回环端口预检被阻断时，不得提交、推送或合并。聚焦测试是 G1/G2 的
正常路径；当影响分类器要求 G3 时不能替代完整门禁。

完成检查会拒绝未归属的改动、证据不完整的矩阵行，以及仍未关闭的 Conformance 行。如果某一
行仅因为当前机器缺少所需操作系统或已安装主机而阻塞，应标记
`blocker_class: "external_environment"`，并在本地 checkpoint 明确使用以下参数：

```bash
bash scripts/pre_submit_gate.sh \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --closure-file task-closure.json \
  --allow-external-environment-blockers
```

该参数不会关闭这条记录，不允许代码或工具失败通过，也不能用于最终受保护分支交付；仍必须
由 CI 或匹配主机完成缺失的验收。聚焦测试不能替代任一门禁。

修改完成技能或门禁本身时分两个检查点：先提交治理-only 的分类注册，再提交受保护的
检查器和集成；不得为了合并这两步而绕过不可变基础分支门禁。

## 文档验证

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

页面还需要检查导航、内部链接、移动布局和浏览器控制台。
