# 测试与质量

## 全量门禁的环境预检

启动全仓 pytest 门禁前，先检查当前宿主是否能绑定回环端口：

```bash
uv run --no-sync python scripts/quality/checks/environment.py
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
uv run --no-sync pytest test/<changed-module>/
uv run --no-sync pytest test/architecture/
# 仅在上方预检返回 0 后运行。
uv run --no-sync pytest test/
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
uv run --no-sync python scripts/governance/boundaries/app_layers.py \
  --project-root . --mode deny-all
uv run --no-sync python scripts/governance/boundaries/system_layers.py \
  --project-root . --mode deny-all
uv run --no-sync pytest test/architecture/
```

App 和系统 Scanner 债务已经清零，两套永久 Scanner 均以 `deny-all` 模式运行，不再使用
旧债基线。未来获批迁移若需要临时精确基线，必须随切片持续缩减并在清零后删除。CI 还会
使用 Pull Request 基础提交中的规则检查候选生产代码，因此同一变更不能放松评判自己的
规则。详见[仓库架构治理契约](../contracts/repository-governance)。

## 质量门

```bash
uv run --no-sync python scripts/quality/checks/python_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit uv run --no-sync pre-commit run --all-files
```

质量基线只容纳已经存在的诊断；新增 Ruff、格式或 MyPy 诊断必须修复，不通过扩大
忽略项或改写基线隐藏。

## 受影响验证与完整后盾

每个 clone/worktree 初始化时安装一次只处理暂存内容的 commit hook：

```bash
bash scripts/quality/hooks/install.sh
```

开发阶段在暂存前运行聚焦测试；`git commit` 随后只检查真实暂存快照：差异空白、锁定版本的
Gitleaks，以及 staged Python 文件的 Ruff check/format。warm 目标为 20 秒；hook 不运行
测试、MyPy、pnpm、Godot、fetch 或任何网络操作，也不安装带测试的 pre-push hook。

普通 push 在 hook 通过后立即开始。精确 PR head 由不可变基础 Manifest 路由；security-fast、
受影响 Python 测试、全仓 Python quality baseline 和其他选中 Lane 并行运行并聚合为
`elfienest/ci-gate`。main 单纯前进不会使该 head 失效；随后原生 merge queue 对合成提交执行
秒级 `elfienest/merge-gate`。`--stage commit` 只保留为显式、可复用的本地 checkpoint，
`--stage push` 是可选的受影响集成重放，两者都不是普通 push 前置条件。

成功的确定性测试检查按命令、作用域输入内容与文件模式、所需不可变基础提交和本机工具计算，
不按交付级别重复记账。合并后/发布完整 Python 后盾
拆为 `app`、`architecture`、`devtools`、`e2e`、`elfie`、`godot`、`infrastructure`、
`nest` 和 `scripts` 九个已注册顶层包。它只运行缺失或失效的包；包输入包含测试和共享
`conftest.py` 的本地 Python 传递 import，只有通过记录、覆盖率片段摘要/版本和可读覆盖率
数据都一致时才能复用。同一次运行共享仓库快照，并在命中前复核签名，最后合并全部片段并
只执行一次全仓覆盖率阈值。一个包失败后，此前通过的包记录仍然保留；下次调用会跳过它们，
从失败或尚未运行的包继续。

需要复用的聚焦检查或完整测试包应通过受控运行器执行：

```bash
.venv/bin/python3 scripts/quality/validation/test_bundles.py \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --selectors test/app/features/setup/
.venv/bin/python3 scripts/quality/validation/test_bundles.py \
  --bundle godot
```

如果 `--selectors` 精确命中一个已注册测试包，它会产生完整后盾使用的同一份带覆盖率证据。
更窄的 node/单文件结果只能按原聚焦命令复用，不能证明所属完整包。原始 `pytest` 只用于
诊断，不产生提交缓存证据。

内部 `--direct-full` 路径会执行完整后盾，但复用有效测试包证据。`--no-cache` 是
明确要求的干净重放：它必须从门禁继续透传到测试包运行器，不能悄悄复用聚焦测试、测试包
或后盾记录。

完整后盾还为其余昂贵工作保存按检查划分的证据。未知可执行输入会使所有测试包失效。缓存位于被忽略的
`build/validation-cache/`，不能替代新 commit SHA 的 CI。

选中预合并 Lane 或 merge gate 失败时不得合并。未知、治理、工具链和锁文件改动通过选择
全部 Lane fail-closed。main 合并后的完整后盾不再串行重跑本地式脚本，而是全选并行 CI
Lane：Python 测试包与 quality、Web、Desktop、Developer Tools、架构、持久化、Godot、
文档、工具链、发布和 Runtime smoke。main 的每条 Lane 使用两个不可取消的奇偶槽，保留
正在运行的工作并合并过期 pending tip。最新 main 为红时隔离普通合并，直到恢复。

### 失败修复阶梯

不要在每次修复编辑后重启宽泛门禁。只有上一层通过，或发现新的依赖边界时才扩大：

1. 只重跑精确失败的 pytest node ID 或失败命令；
2. 它通过且执行代码发生变化后，再跑所属测试文件或模块；
3. 只有对应边界发生变化，才跑直接受影响的集成或架构检查；
4. 由选中的精确 SHA CI Lane 证明候选；只有诊断 main 健康或准备发布时才运行 full。

同一源码状态下不得重复成功命令。怀疑环境或偶发失败时，可以写明理由后诊断性重跑一次，
但不能因此重启整套测试。每次扩大范围都必须指出新增风险、改动依赖或交付阶段。

仍未关闭的 Conformance 行必须保留缺失证据和下一步主机/CI 验收，不得在本地报告为完成。
这类外部条件不是本地实现失败，但也不能替代最终受保护分支交付所需的验收。聚焦测试不能
替代任一门禁。

## 文档验证

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

页面还需要检查导航、内部链接、移动布局和浏览器控制台。
