# Nest–Godot 语义世界一致性

> [Nest–Godot 语义世界契约](../contracts/nest-godot-semantic-world)的临时迁移台账。
> 它只记录当前实现缺口、执行顺序和关闭缺口所需证据，不削弱或重定义目标。

## 为什么重新打开台账

原台账在协议 v3 产品迁移中被删除，一致性索引也被改成 Nest–Godot 债务为零。之后按
契约条款和实际目录重新审查发现：传输和部分结构已经迁移，但多项语义、恢复与清理门槛
从未被证明。测试通过不能支持删除台账：

- 部分测试断言的是现有“双事件/原始队列”行为，而不是契约规定的唯一线路；
- 同区域正向案例不能证明真实物理可见性或可听性；
- 架构测试保护 import 与类型边界，不证明完整生产者到消费者行为；
- 一次涉及 141 个文件的迁移，把原计划要求独立关闭的工作混在一起。

因此撤销“零债务”结论。下面每一行都保持 open，直到当前代码满足关闭条件。

## 目标源码归置

Nest 的四个所有者是业务边界。公共聚合支撑不是第五个所有者，技术性大杂物包也不能
代替事实所有权。

| 当前 Nest 路径 | 目标归置 |
| --- | --- |
| `nest/nest.py` | 保留稳定 `Nest` Facade 和聚合装配；吸收或私有化宽泛的 `NestState` 兼容壳。 |
| `nest/space/` | 把真实行为迁入名称明确的 `nest/space_facilities/` 所有者包。 |
| `nest/rules/` | 把真实行为迁入名称明确的 `nest/living_rules/` 所有者包。 |
| `nest/time_environment/` | 保留时钟、生活阶段、定时规则、期望环境及时间/环境驱动。领域名仍是**时间与环境**，不改叫 `engine`。 |
| `nest/interaction/` | 把说话、视觉、语义行动的短期关联与拼装迁入 `nest/elfie_interaction/`；不得再保存第二套投递队列。 |
| `nest/events.py` | 保留跨所有者类型化事件机制；它不是业务所有者。 |
| `nest/engine/` | 把负 Tick 规则和调用方并回时间与环境后删除；它不是独立 Nest 职责。 |
| `nest/state/store.py` | 调用方全部使用 `Nest` Facade 与真实所有者状态后删除兼容壳。 |
| `nest/state/models.py`、`errors.py` | 类型和错误回到定义其含义的所有者；只有真正跨所有者的类型才留在根边界。 |
| `nest/state/config.py` | 仍有必要时移为 `nest/config.py`。 |
| `nest/state/repository.py` | 按 ADR-0016 拆分：技术无关的快照语义和 Facade 导出/恢复留在 Nest；存储 Port 与应用错误迁入 `app/orchestration/nest_session/`；具体 SQL/SQLite 继续位于 `infrastructure/persistence/`。不得创建 `nest/persistence.py`。 |

Godot 目录表达源码类别，不对应 Nest 的业务模块。下列归置既避免误删场景内容，也避免
把开发材料打进发布包。

| Godot 路径类别 | 归置 |
| --- | --- |
| `main.gd`、`main.tscn` | 只负责装配和模式分派；无引用 Helper 经证据确认后删除。 |
| `rooms/`、`characters/` | 保留物理场景、几何、角色资源和运行资产；它们是内容，不是多出的业务模块。 |
| `runtime/actor/`、`runtime/world/`、`runtime/endpoint/` | 保留少量 ElfieNest 自有 authority 胶水；物理可见性和可听性归 `world`，不归 Actor Controller。 |
| `runtime/observer/`、`runtime/lab/`、`ui/`、`lab_preview_controller.gd` | 只保留有引用的 Observer/Lab 展示行为；不拥有物理或家庭 authority，不为追求形式对称强制改名。 |
| `scripts/test/`、`scripts/tools/`、`characters/tools/`、角色 `source/` 树 | 作为测试、创作或开发输入；正确区分 audit/render 脚本，并从所有发布导出中排除。 |
| 无引用 Helper、参考场景、被忽略 source 下的 `.import` 边车 | 逐项审查；只有 Scene、preload、CLI、文档及导出引用都不存在时才删除。 |

## 当前缺口

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| NGW-R01 | P0 | open | `nest/engine/` 重复 `TimeEnvironmentState.advance()`；宽泛 `nest/state/` 混合聚合装配、配置、全部所有者模型/错误和持久化 Port；`NestState` 仍是公开兼容表面。 | 无兼容 import 地完成上述目标归置；`Nest` 是稳定 Facade；每类事实/类型只有一个所有者；Nest 聚焦测试和 import 扫描通过。 | pending |
| NGW-R02 | P0 | open | 类型化 `NestEventEnvelope` 只由交互线路产生，而说话和视觉同时进入每居民原始感知队列；生产代码消费原始队列，兼容说话方法绕过 Envelope。 | 四个所有者都可使用同一公共机制；一个生产消费者只投递一次类型化定向事件；删除原始/兼容投递路径；重复与禁止线路测试通过。 | pending |
| NGW-R03 | P0 | open | `SemanticActionResult` 可能只留在 Outbox，没有生产消费者投递给目标 Elfie；说话和视觉被转成扁平 Body Payload，说话表露情绪丢失。 | `HeardUtterance`、`SemanticVisualScene`、`SemanticActionResult` 以结构化 Payload 到达目标 Elfie；情绪和因果身份保留；各自具有正向、非目标与去重测试。 | pending |
| NGW-R04 | P0 | open | 当前会拒绝部分旧 generation 输入并重发期望环境，但居民/环境投影没有统一来源标记，说话/视觉/行动待处理关联没有统一失效，旧实际状态可跨 authority 换代残留。 | 每份保留的物理投影携带 Runtime/generation/revision；换代统一失效旧投影并只中断一次待处理关联，只同步当前期望状态；陈旧输入和恢复测试通过。 | pending |
| NGW-R05 | P1 | open | 生活规则已实现成员、Home 分配和床位冲突，但尚未实现已接受的共享、预约、占用、访问、受众规则和环境覆盖决策。 | 只实现当前产品流程真正需要的最小家庭规则，仍是一名家庭管理员，不增加企业角色/审批系统；说话/事件受众与语义行动共用同一规则。 | pending |
| NGW-R06 | P0 | open | Godot 视觉只按同区域加固定距离筛选，且位于 Actor Controller；没有视野角度、遮挡或当前物理可见性判断。 | World 所有的空间查询使用 Actor Transform、有界距离、FOV、Ray/空间遮挡和当前状态；真实 Godot 测试覆盖目标、身后、遮挡、超距、数量上限和旧 generation。 | pending |
| NGW-R07 | P0 | open | Godot 说话可达把同一区域其他 Actor 全部选中；声学 Profile 只校验值，不影响距离或传播，门/遮挡被忽略。 | World 所有的可听性应用约定的距离/Profile/阻挡模型，只返回候选；测试覆盖同区但听不到、超距、阻挡、Profile 和重试；内容与最终居民受众仍由 Nest 拥有。 | pending |
| NGW-R08 | P1 | open | 环境能力只是粗粒度灯光/安静状态；实际状态和时间/环境的期望状态放在一起，也不是以稳定对象为键、带来源的投影。 | 每个已支持的有状态对象/组拥有稳定 ID、类型化期望命令和实际事实/结果；实际投影归空间与设施并带来源；恢复只重发当前期望状态。没有获批行为的对象不写脚本。 | pending |
| NGW-R09 | P1 | open | 声音可达和视觉观察写在 `runtime/actor/actor_controller.gd`；尽管已有 World 与 `spatial_queries.gd`，Actor 仍同时拥有身体执行和 Actor 相对世界查询。 | Actor 只拥有身体执行，World 拥有声音/视觉空间查询；现有 Python 窄能力和 Bootstrap 创建的唯一共享 Gateway 保持不变。 | pending |
| NGW-R10 | P1 | open | Godot 导出使用 `all_resources`，却只排除两个 source Glob，测试/工具/创作资源可能进入发布包；被忽略的创作 Source 仍有已跟踪 Import 边车，多项无引用候选也未分类。 | 发布输入改为 Allowlist 或完整排除开发/创作树；发布 Manifest 证明边界；每个候选被归类为有引用、保留创作源或删除，且不破坏场景/资源/测试引用。 | pending |
| NGW-R11 | P1 | open | 台账曾被提前删除且索引宣称零债务；ADR-0015 已为该失败模式增加机器门禁，但部分当前 README 仍与契约的事实所有权和事件线路矛盾，最终收口证据也尚不存在。 | 当前架构/README 与已验证实现一致；基线感知删除和证据门禁持续通过；其他各行均以完整证据关闭后，才由独立治理变更删除双语镜像和注册项。 | pending |
| NGW-R12 | P0 | open | ADR-0016 已固定目标，但 `NestRepository`、错误和 `NestPersistenceSnapshot` 仍由 Nest 导出；App Orchestration 拥有全部生产调用，并在恢复时直接修改宽泛 `nest.state`。 | Nest 暴露技术无关的 `NestSnapshot` 和 Facade 导出/恢复操作；App Nest Session 拥有 `NestStateStorePort`、持久化时机和应用错误；Infrastructure 实现它；全部调用方及严格边界测试同一切片迁移，不再导出 Nest Repository，也不再深层修改状态。 | pending |

## 约束性的迁移顺序

实施必须使用独立批准、可单独审查的切片。一阶段要把真实生产者、类型边界、消费者和
聚焦证据一起迁移完，才能进入下一阶段。

1. **NG-R1—唯一事件投递（`NGW-R02`、`NGW-R03`）。** 建立唯一生产 Nest 事件
   消费者，保留结构化语义 Payload，然后删除原始感知队列和兼容说话投递。
2. **NG-R2—Generation 与恢复（`NGW-R04`）。** 所有保留物理投影增加来源，并用一条
   authority 换代路径统一失效投影与待处理语义关联。
3. **NG-R3—家庭决策（`NGW-R05`）。** 实现产品场景真正使用的最小共享、访问/占用、
   受众及环境覆盖行为，不增加企业治理。
4. **NG-R4—物理感知（`NGW-R06`、`NGW-R07`、`NGW-R09`）。** 空间操作移入 World，
   用真实 Godot 负例证明 FOV/遮挡/距离与可听性。
5. **NG-R5—环境对象（`NGW-R08`）。** 先完成一个真实有状态环境能力的端到端闭环，
   再只增加产品实际需要的对象。
6. **NG-R6—Nest 结构清理（`NGW-R01`、`NGW-R12`）。** 实施 ADR-0016 的快照/Port
   拆分；行为已有唯一所有者和线路后，再按获接受的归置删除 `engine/`、拆掉 `state/`；
   本阶段必须不改变行为。
7. **NG-R7—Godot 源码/导出清理（`NGW-R10`）。** 先分离发布输入和测试/创作输入，再
   删除确证的死产物与 Helper；不能因为不属于业务模块就删除场景/角色内容。
8. **NG-R8—当前文档与收口（`NGW-R11`）。** 完整运行直接身体、语义行动、视觉、说话、
   环境、生命周期场景；更新当前事实文档；所有行真实关闭后，才用独立治理变更删除台账。

## 关闭任一缺口前必须具备的证据

每类受影响语义事实都要有一行可追踪矩阵，明确：

1. 精确契约条款和语义所有者；
2. 真实生产者与类型化边界；
3. 唯一生产线路与最终消费者；
4. 正向场景，以及明确的非目标/禁止线路场景；
5. 重试/去重身份；涉及物理状态时还必须包含旧 generation 与恢复行为；
6. 被替换线路或产物已经消失的源码/引用证据；
7. 声称 Godot 行为或发布边界时的真实 Godot 或发布导出证据。

一行关闭时，其 `证据` 单元格必须用简洁的 `target=`、`inventory=`、`references=`、
`verification=` 和 `residuals=` 引用替换 `pending`，并覆盖上述材料。

单元测试、传输 Round Trip、目录名或截图中的任意一项都不足以单独关闭缺口。只要还有
一行 open，就不得删除本台账及其双语注册项。
