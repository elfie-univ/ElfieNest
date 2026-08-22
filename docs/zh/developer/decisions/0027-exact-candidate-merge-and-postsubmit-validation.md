# ADR-0027：精确候选合并门与合并后完整验证

- **状态：** 已接受
- **日期：** 2026-08-22
- **范围：** Pull Request 路由、合并队列、main 健康和发布验证
- **取代：** ADR-0023 中受保护主线必须前置 G3 的部分

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
  版本化受影响路径 Manifest。未知可执行、治理和工具链改动选择全部 Lane；security-fast
  永远执行。
- 并行运行选中的 Python、Web、Desktop、Developer Tools、架构、持久化、Godot、文档和
  工具链 Lane，先聚合为 `elfienest/ci-gate`，再只把跨事件稳定的
  `elfienest/merge-gate` 绑定到分支保护。Pull Request 上该必需检查等待聚合结果；合并组上
  同名检查执行轻量合成提交验证。选中 Lane 缺失、跳过、取消或失败时聚合检查必须失败。
- 不因 main 前进而 rebase 或重跑受影响测试。只有候选 SHA 变化或真实冲突才使证据失效。
- 使用 GitHub 原生 `merge_group` 事件生成 `elfienest/merge-gate`，初始每组一个 Pull
  Request。合并门检查精确身份、基础/Ref、父提交、差异洁净和门禁 Schema；不安装依赖，也
  不重跑产品套件。
- 每次 main push 后及显式 full/发布 dispatch 执行完整 G3。main 运行不可取消，使用两个
  奇偶槽保留正在运行的工作并合并过期 pending tip；已被新 commit 取代的 PR head 可以取消。
- 最新 main tip 完整后盾终态为红时隔离普通合并；只允许受审计且范围明确的修复或回滚，
  直到更新 main 的绿色结果取代红灯。
- live GitHub Ruleset 必须要求 Pull Request、merge queue、稳定检查、禁止直接/强制 Push，
  并要求治理/CI 维护者审查。仅凭仓库源码不能声称这些外部状态已生效。

## 被拒绝方案

- **每次合并前保留完整 G3：** 广覆盖仍在，但违反十分钟目标并传播无关失败。
- **持续把当前 main 合入/rebase 每个候选：** 把正常 main 移动变成证据抖动，无法随贡献者
  数量扩展。
- **现在自建 Landing Service：** 可以产生 App 自有精确合并检查，但会新增凭据、部署和恢复
  所有权；当前仓库已有 GitHub 原生 merge queue。
- **删除广覆盖验证：** 以丢失检测换速度。完整后盾只是移动位置，没有被削弱。

## 影响

普通改动只等待受影响证据和秒级合成合并检查。Medium/Large 工作在开发期间对精确候选完成
必需证据，不在 submit 命令后才开始。合并后验证可能发现 main 的短暂回归；隔离加聚焦修复/
回滚是明确的控制机制。平台故障不计入 SLO，必须报告而不能绕过。

切换前必须以代表性历史做 Shadow 重放、已知 Lane 零漏选、p95 时间满足契约并验证 live
Ruleset。在此之前保留旧完整入口，Ruleset 维持 Evaluate。
