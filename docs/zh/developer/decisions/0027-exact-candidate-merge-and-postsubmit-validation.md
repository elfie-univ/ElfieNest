# ADR-0027：精确候选合并门与合并后完整验证

- **状态：** 已接受
- **日期：** 2026-08-22
- **修订：** 2026-08-23
- **范围：** Pull Request 路由、合并队列、main 健康和发布验证
- **取代：** ADR-0023 中受保护主线前置 G3 及普通本地 G1/G2 交付阶段强制要求
- **由 ADR-0029 细化：** 显式 Git 授权、单 PR 交付与 PR 前证据复用

## 背景

ElfieNest 曾把完整仓库后盾设为每次 main 交付的前置条件。因此，微小前端或文档改动也要
在本地承担无关 Python、Godot、工具链和文档工作；任一无关红灯还会阻塞所有贡献者。并发
开发时反复把持续移动的 main 合入已验证候选，又会使证据失效并造成无尽重试。

大型项目不会让每个贡献者跑全仓时占住 main。成熟的受影响测试体系会并行验证候选，只
串行化最终写入，执行短暂的精确合并检查，并保留合并后、夜间和发布广覆盖。OpenClaw 的
可信预检、聚合检查和 main 奇偶槽是主要运行参考；GitHub 原生 merge queue 为 ElfieNest
提供精确合成提交。

## 决策

- 把阻塞合并的证据绑定到精确 Pull Request head SHA。使用不可变基础提交中的分类器生成
  版本化受影响路径 Manifest。未知可执行、机器信任根和工具链改动选择全部 Lane；纯治理
  说明只选择治理、文档与架构审查 Lane。security-fast 永远执行。
- 保持 `scripts/bootstrap.sh` 为稳定 Bootstrap/工具链入口。`scripts/internal/bootstrap/`
  通过 fail-closed 工具链分类，`scripts/internal/build/` 与 `scripts/internal/release/`
  通过 fail-closed 发布分类；内部诊断脚本继续选择受影响 Python Lane。内部迁移不新增根目录
  兼容壳；架构覆盖递归发现脚本源码，并按辅助脚本逻辑身份或目标分类定位，不冻结即将废弃
  的根目录位置。
- 安装仓库管理且只处理暂存内容的 pre-commit hook。warm 路径在 20 秒内执行差异空白、锁定
  版本 Gitleaks 和 staged Python Ruff，不运行测试、MyPy、Node、Godot、fetch 或网络操作。
  普通 push 不设置带测试的 pre-push 门禁；显式受影响本地 stage 只保留为诊断工具，不作为
  交付前置条件。
- 把锁定的开发工具和仓库管理的 hook 一并作为源码开发就绪条件。普通启动器通过现有幂等
  `ensure --tier=dev` 路径修复缺失 hook；非 Git 源码归档跳过 hook 安装，也绝不假定 clone
  已经自动执行仓库代码。
- 并行运行选中的 Python、Web、Desktop、Developer Tools、架构、持久化、Godot、文档和
  工具链 Lane，先聚合为 `elfienest/ci-gate`，再只把跨事件稳定的
  `elfienest/merge-gate` 绑定到分支保护。Pull Request 上该必需检查等待聚合结果；合并组上
  同名检查执行轻量合成提交验证。选中 Lane 缺失、跳过、取消或失败时聚合检查必须失败。
- 把 Python 正确性与 Python 静态质量拆开：受影响确定性测试与全仓 Ruff/format/MyPy 基线是
  两条并行 Lane。Python 源码/测试同时选择两者；纯前端改动不选择 Python quality，除非治理、
  工具链或未知分类 fail-closed。
- 不因 main 前进而 rebase 或重跑受影响测试。只有候选 SHA 变化或真实冲突才使证据失效。
- 对用户明确放行的最终候选，在创建单一 PR 前从受信任 main Workflow 运行一次受影响图。
  只有候选、基础治理、Manifest、工具链与 Workflow 身份完全匹配时才在 PR 复用，否则正常
  运行选中图。
- 使用 GitHub 原生 `merge_group` 事件生成 `elfienest/merge-gate`，初始每组一个 Pull
  Request。合并门检查精确身份、基础/Ref、父提交、差异洁净和门禁 Schema；不安装依赖，也
  不重跑产品套件。
- 每次 main push 后及显式 full/发布 dispatch 通过全选现有 Lane 并行执行完整图，包括 Python
  测试包与 quality、Web、Desktop、Developer Tools、架构、持久化、Godot、文档、工具链、
  发布和 Runtime smoke。main 的每条 Lane 使用两个不可取消的奇偶槽，保留正在运行的工作并
  合并过期 pending tip；已被新 commit 取代的 PR head 可以取消。
- 在 CI Summary 记录候选、PR 证据核验与 full 图耗时。十分钟 p95 从用户放行稳定最终候选
  开始，到 main 核验完成为止，不按 PR 重新计时；候选 CI 预算 7 分钟，单一 PR 加 queue/ref
  核验预算 3 分钟。目标依赖足够的外部 Runner 容量；容量不足是运维阻塞，不能成为跳过
  选中 Lane 的理由。
- 最新 main tip 完整后盾终态为红时隔离普通合并；只允许受审计且范围明确的修复或回滚，
  直到更新 main 的绿色结果取代红灯。
- live GitHub Ruleset 必须要求 Pull Request、merge queue、稳定检查并禁止直接/强制 Push；
  出现第二名已验证维护者后，还必须要求治理/CI 路径级独立审查。仅凭仓库源码不能声称这些
  外部状态已生效。

## 运行澄清：受影响 Lane 被跳过时

candidate-evidence 发布器位于受影响路径验证图之后。该图会有意跳过与候选无关的 Lane，
因此发布器必须使用 `always()` 计算 dispatch 条件，再显式要求 `preflight` 和
`merge-gate` 成功。这样可以把被跳过的无关 Lane 排除在发布器的隐式 success 判断之外；
这不把选中的 skipped Lane 视为成功，因为 `elfienest/ci-gate` 仍会拒绝选中 Lane 缺失、
跳过、取消或失败。本澄清不改变验证范围或分支保护要求。

## 被拒绝方案

- **每次合并前保留完整 G3：** 广覆盖仍在，但违反十分钟目标并传播无关失败。
- **持续把当前 main 合入/rebase 每个候选：** 把正常 main 移动变成证据抖动，无法随贡献者
  数量扩展。
- **现在自建 Landing Service：** 可以产生 App 自有精确合并检查，但会新增凭据、部署和恢复
  所有权；当前仓库已有 GitHub 原生 merge queue。
- **删除广覆盖验证：** 以丢失检测换速度。完整后盾只是移动位置，没有被削弱。

## 影响

普通改动只等待受影响证据和秒级合成合并检查。更广改动在开发阶段与选中 CI Lane 中对精确
候选完成必需证据，不在 submit 命令后才开始。合并后验证可能发现 main 的短暂回归；隔离加聚焦修复/
回滚是明确的控制机制。平台故障不计入 SLO，必须报告而不能绕过。

单 PR merge group 刻意不在合成提交上重跑全部产品套件；如果不恢复长时间队列测试，两个单独
绿色改动之间的语义干扰就不可能降为零。秒级身份检查、main 异步完整图和立即隔离是已接受的
控制方式；不得把这一残余描述成“并发语义冲突不可能发生”的证明。

切换要求已知 Lane 零漏选、耗时遥测满足契约、live Ruleset 已验证且 Runner 容量充分。显式本地
full 入口继续用于发布/诊断，但不是普通 push 门禁。
