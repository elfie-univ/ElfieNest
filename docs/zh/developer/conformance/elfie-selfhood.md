# Elfie Selfhood 一致性台账

> 状态：第一阶段实现已落地；观察投影所有权、模型行为与既有 workspace 迁移仍开放<br>
> 基线：2026-08-30，`91c26643`<br>
> 目标：[Elfie Selfhood 与固定模型头部设计](../designs/elfie-selfhood-and-fixed-model-header.md)<br>
> 契约：[Elfie 2.3](../contracts/elfie.md) 与 [Brain 1.5](../contracts/brain.md)

这份临时台账记录第一阶段 Selfhood/固定头部实现切片之后仍然存在的源码与验收差距。
标记为 closed 的行只在本阶段范围内关闭；开放行仍需完成各自行规定的证据，结构性单元
测试不能替代这些证据。

## 台账

| ID | 严重级别 | 状态 | 当前状态 | 目标与关闭门 | 证据 / 残留 |
| --- | --- | --- | --- | --- | --- |
| SHD-001 | P0 | closed (phase 1) | 运行时 Selfhood 已使用严格 `SelfhoodState`，语义上严格含 `identity_core` 与 `adaptive_self` 两层；Genesis 在创建 Bundle 中校验完整 typed sibling。 | 保持闭合两层 schema 与确定性 Genesis 并列物化；拒绝不完整/不一致 Bundle。 | `test/elfie/brain/selfhood/test_system.py`、`test/elfie/genesis/test_contracts.py` 与 workspace/adoption 测试；28 个 Selfhood/Memory 聚焦测试与 22 个 workspace/Genesis 测试通过。Genesis 仍保留 `PersonalitySeed`/`SelfModelSeed` 仅用于生成普通 Genesis Memory，不是运行时 Selfhood authority。 |
| SHD-002 | P0 | open | 普通 Reasoning 已正确只接收 `SelfhoodPromptProjection`，旧 fallback 已删除，Selfhood 缺失也会在 ModelPort 前阻止认知。但 `elfie/brain/selfhood/contracts.py` 仍拥有含世界/物种 Canon、知识边界和赴地字段的 `ProfileAnchorSnapshot`，`elfie/facade_operations.py` 还会按当前代码 Canon 刷新它；这是藏在 Selfhood 所有权里的 Profile/App 投影。 | 保持已经成立的运行期不读、不 fallback 和 fail-closed 行为；从 Selfhood 删除 Profile/Canon Observer 合同，只暴露稳定 Profile 档案或 App 聚合 View。以递归所有权/引用测试和 Observer 行为证据证明不再刷新当前 Canon，也不进入 Brain。 | target=Brain 1.5 Selfhood/Genesis 条款与 ADR-0033；inventory=Selfhood 合同/导出、Facade Observer、Profile Canon 及全部调用方；verification=待完成所有权扫描、Reasoning 与 Observer 回归；residuals=运行期不读已经成立，投影所有权尚未收口。 |
| SHD-003 | P0 | closed (structural) | required bundled `ReasoningConstitution` 已由 Bootstrap 加载；Brain 组装准确四段固定前缀，把动态工具/schema 放进 `TURN_PROTOCOL`；Provider Adapter 与 Prompt Injector 保留 Brain 的 system 内容。 | 保持准确顺序、单一 Constitution 来源和同一 Run 字节稳定；未来 Provider 专项检查继续接入 Adapter 门禁。 | `config/brain/reasoning-constitution.yaml`、配置注册/发行清单、`elfie/brain/reasoning/model_header.py`、固定头部测试与不注入测试通过。模型 Provider 实际行为与完整 context-window 证据仍独立于结构门禁。 |
| SHD-004 | P0 | open | 确定性 projection 已渲染审阅过的自然语言并拒绝控制符/分隔符/头部注入；不输出大五原始值、opaque ID、证据或传记。 | 除确定性 projection 测试外，还必须完成盲测支持模型行为矩阵后才能关闭。 | `elfie/brain/selfhood/system.py`、`SelfhoodPromptProjection`、固定头部测试覆盖 projection/注入/无原始人格字段 fixtures。本切片未运行真实模型实验；不宣称数字人格行为已验证。 |
| SHD-005 | P0 | closed (phase 1) | 每只 Elfie 的 `brain/selfhood.yaml` 是唯一运行时 Selfhood seed；通用 continuity 不含 Orientation/Selfhood 字段，projection 不持久化，Memory 的权威自我叙事已删除。 | 保持单一来源与重启 fail-closed 行为。 | `elfie/brain/continuity.py`、`elfie/brain/runtime.py`、`elfie/brain/memory/`、固定头部测试和 journal recovery tests 覆盖边界；生产引用递归扫描干净。既有 workspace 仍可能含旧 checkpoint/`core_*` 数据；迁移见 SHD-007。 |
| SHD-006 | P0 | closed (phase 1) | `propose_update`、candidate 校验与 commit 已用 `SelfhoodGrowthDisabledError`/拒绝封口；没有装配 Turn、Activity、Emotion、Orientation 或模型 writer。 | 在强类型 Memory proposal 与原子存储单独获批前保持 growth disabled。 | `elfie/brain/selfhood/system.py`、settlement/consolidation wiring 与 Selfhood tests 覆盖直接 writer 拒绝和无运行时 writer 扫描。成长频率、算法、阈值、proposal schema 与持久 commit 仍是后续工作。 |
| SHD-007 | P0 | open | 既有 resident workspace 可能同时含旧扁平 YAML、Selfhood journal checkpoint 与 Memory `core_*` 节点。尚无获批盘点决定它们分别重建、转换、降为普通 Memory 还是删除。 | 任何生产 rollout 前，必须冻结真实数据盘点并批准一套可恢复迁移/重建政策。只有备份/回滚、混合版本拒绝、安装包升级和代表性真实 workspace 证据齐全才能关闭；不得 Profile/Canon fallback 或静默破坏性重置。 | 本阶段不做迁移或破坏性重置。开发测试数据只能按仓库现有开发数据规则重建。 |

SHD-002、SHD-004 与 SHD-007 仍开放，因此台账尚未准备收口。closed 行只表示第一阶段边界已实现，
不授权静默迁移既有用户 workspace，也不代表模型行为质量已验证。
