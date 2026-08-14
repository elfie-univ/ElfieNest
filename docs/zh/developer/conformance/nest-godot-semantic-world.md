# Nest–Godot 语义世界一致性

> [Nest–Godot 语义世界契约](../contracts/nest-godot-semantic-world)的临时迁移台账。
> 它只记录当前实现缺口、执行顺序和关闭缺口所需证据，不削弱或重定义目标。

## 为什么曾重新打开台账

原台账在协议 v3 产品迁移中被删除，一致性索引也被改成 Nest–Godot 债务为零。之后按
契约条款和实际目录重新审查发现：传输和部分结构已经迁移，但多项语义、恢复与清理门槛
从未被证明。测试通过不能支持删除台账：

- 部分测试断言的是现有“双事件/原始队列”行为，而不是契约规定的唯一线路；
- 同区域正向案例不能证明真实物理可见性或可听性；
- 架构测试保护 import 与类型边界，不证明完整生产者到消费者行为；
- 一次涉及 141 个文件的迁移，把原计划要求独立关闭的工作混在一起。

“零债务”结论仍由本台账守护。实现切片及其证据现已完成，下面每一行均已 closed；本台账
暂时保留注册，等待 NGW-R11 所述的独立治理变更删除双语镜像。

## 2026-08-15 最新收口审查

最近一次契约审查提出的七项问题已按以下顺序关闭。这里记录具体实现和证据，不把目录名
或一次通过的单元测试单独当作线路、所有权或清理完成的证明。

| 问题 | 已关闭的实现 | 证据 |
| --- | --- | --- |
| Elfie、Nest、Godot 之间的语义行动身份可能丢失 | Gateway、Nest Session、Actor Controller 和结果 Payload 统一要求 `intent_id`、`body_generation`、Actor 身份及 `initiator=elfie`。 | 协议、分类入站、Native Body、Nest、Runtime workflow 测试；mypy 与架构扫描通过。 |
| Snapshot 恢复可能残留旧居民和投影 | `Nest.restore_snapshot()` 现在替换居民、Home、Runtime mirror 和交互待处理状态，保留 AWAY 与显式 reconciliation。 | `test_restore_snapshot_replaces_residents_and_restores_presence` 及 Nest/session 持久化测试。 |
| 旧的 raw vision/audio/environment sensors 仍存在 | 删除旧 sensors 包及测试；Nervous System 和公开 API 只使用规范化类型语义事件。 | 仓库引用扫描不再发现退役 sensor 符号；Elfie nervous-system/body 套件通过。 |
| 设施视觉绕过 Godot 空间查询边界 | Godot 发布设施 marker，并和 anchor 共用距离/FOV/遮挡过滤路径。 | Runtime interaction/navigation headless 契约通过；没有新增 Camera3D、截图或媒体路径。 |
| 非交互 Nest 所有者没有统一的类型化事件生产路径 | Space and Facilities、Living Rules、Time and Environment 通过公共 outbox 产生 `NestFactNotice`；受众仍由 Living Rules 解析。 | Nest owner-event 与 Runtime delivery 测试覆盖目标过滤、类型 Payload 和去重。 |
| Observer camera reset 测试依赖环境隐含前提 | 前端测试显式设置 secure-context 前提。 | Web 前端 105 个文件/498 个测试通过；typecheck 和生产构建通过。 |
| 未完成完整 inventory 就宣称目录/契约收口 | 重新执行结构、有效依赖、System 层和 App 层扫描，并分类 tracked/generated/support；Godot headless 检查后无未跟踪文件。 | 四项扫描均报告 0 个 forbidden target；无未跟踪文件或退役 sensor 引用。 |

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

## 已关闭的一致性条目

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| NGW-R01 | P0 | closed | 已删除临时 Nest 容器，事实、模型和错误均回到对应所有者。 | 目录、Facade 和旧导入清单由结构扫描器与项目结构测试守护。 | target=Nest 所有权条款；inventory=nest 根及四个所有者目录；references=无旧包或 NestState 调用方；verification=54 个聚焦测试及 49 个源文件 mypy 通过；residuals=none |
| NGW-R02 | P0 | closed | 类型化 Nest 事件投递已成为唯一生产线路，也覆盖所有者产生的事实通知。 | 交互关联和四个所有者只产生一份类型化 Envelope；路由解析明确受众，并按同一事件身份重试。 | target=公共事件机制；inventory=nest/events.py、nest/elfie_interaction/hub.py、Nest 所有者生产者和编排路由；references=事件线路及退役 sensor 扫描；verification=Nest owner-event、说话、视觉和 workflow 的重复/非目标测试通过；residuals=none |
| NGW-R03 | P0 | closed | 结构化听觉、视觉和语义行动 Payload 在投递中保留情绪、因果、目标及 intent 身份。 | 生产消费者向所属 Elfie 各投递一次 Envelope，也支持类型化 `NestFactNotice`。 | target=结构化语义感知条款；inventory=events.py、hub.py、body contracts、world_perception.py；references=类型化投递和协议身份测试；verification=正向、非目标、重试和去重场景通过；residuals=none |
| NGW-R04 | P0 | closed | 居民、环境和交互待处理状态统一带 Runtime/generation/revision 来源，并走一条 authority 换代失效路径。 | 陈旧帧被拒绝；Snapshot 恢复是替换而非合并；只重新同步当前期望环境。 | target=generation 与恢复条款；inventory=runtime_sync、runtime_events、Nest restore 和 interaction invalidation；references=陈旧/恢复/restore workflow 测试；verification=最新 origin/main 上全仓 Python 2350 个测试通过、3 个跳过；residuals=none |
| NGW-R05 | P1 | closed | 巢内生活规则统一拥有成员、Home、共享/访问、占用、受众过滤和环境覆盖决策，不引入企业角色。 | 语义行动和事件受众都调用同一 Nest 规则。 | target=巢内生活规则所有者；inventory=living_rules 与 Nest Facade；references=Home、受众和覆盖调用方；verification=Nest/workflow 测试通过；residuals=none |
| NGW-R06 | P0 | closed | Godot World 拥有有界视觉空间查询，只返回候选，不把媒体或坐标带入 Nest。 | Anchor 和 facility marker 共用距离/FOV/遮挡路径；没有每个精灵的 Camera3D 或 screenshot/VLM 路径。 | target=Godot 空间查询条款；inventory=rooms/nest.gd、runtime/world 和空间查询测试；references=Actor 无世界查询所有权路径及退役 sensor 扫描；verification=Godot scene、environment、interaction、navigation headless 契约通过；residuals=none |
| NGW-R07 | P0 | closed | Godot World 计算说话可达候选，Nest 保留内容、情绪和最终居民受众规则。 | 说话走类型化 Nest Bridge；只向 Godot 候选中经 Living Rules 过滤后的听者投递，不走 Elfie TTS/STT。 | target=SpeechBridge 条款；inventory=runtime/world、gateway、interaction hub 和 body contracts；references=协议身份和说话 workflow 测试；verification=Godot Runtime interaction 契约及定向/重试投递测试通过；residuals=none |
| NGW-R08 | P1 | closed | 环境实际状态现在是由空间与设施拥有、带 Runtime 来源的稳定 `nest/environment` 对象投影。 | 期望状态仍由时间与环境拥有，恢复只重发该期望状态。 | target=EnvironmentChannel 条款；inventory=space_facilities 模型/目录、Adapter 和 Godot environment controller；references=对象 ID 校验；verification=29 个环境/持久化测试及 Godot Runtime 验证通过；residuals=none |
| NGW-R09 | P1 | closed | Actor 代码只执行身体动作；World 和 `spatial_queries.gd` 拥有视觉/声音查询，Gateway 仍由 Bootstrap 唯一创建。 | 没有新增 Python 物理镜像或第二 Gateway。 | target=Godot authority 条款；inventory=godot_project/runtime 与 infrastructure/godot；references=World 所有权静态扫描；verification=Runtime Observer 和场景路径测试通过；residuals=none |
| NGW-R10 | P1 | closed | Web 和 Linux Dedicated 导出预设共享完整的开发/创作排除边界，生成 Manifest 记录该边界。 | 创作源候选已分类，source 树中已跟踪 `.import` 边车已清理。 | target=导出边界条款；inventory=导出预设、export_boundary.py 和 source 候选；references=22 个导出/Runtime 测试及 source `.import` 数为零；verification=Manifest 与引用扫描通过；residuals=none |
| NGW-R11 | P1 | closed | README 的所有权和线路描述已与四所有者实现一致；台账仍注册，等待独立治理删除。 | 以完整 tracked/generated/support inventory 重跑结构、有效依赖和层扫描，不从测试结果推断收口。 | target=ADR-0015 收口生命周期；inventory=中英文契约、README、全部 Nest/Godot 路径、扫描器和台账；references=双语行状态、退役路径扫描和当前主分支审查；verification=治理/架构套件及四项 deny-all 扫描通过；residuals=none |
| NGW-R12 | P0 | closed | Nest 只暴露 `NestSnapshot` 与 Facade 导出/恢复；App 拥有 `NestStateStorePort` 和时机；SQLite 仍在 Infrastructure。 | 不再导出 Nest Repository、深层修改 `nest.state` 或保留旧 sensor 持久化。 | target=ADR-0016 持久化所有权；inventory=Nest snapshot、App ports/session 和 SQLite Adapter；references=旧 repository/state 与 sensor 导入扫描；verification=持久化/workflow 测试、mypy 及 system-port 架构门通过；residuals=none |

**收口状态：** ready

## 已完成的迁移顺序

实施已使用独立批准、可单独审查的切片。每个阶段都把真实生产者、类型边界、消费者和
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
8. **NG-R8—当前文档与收口（`NGW-R11`）。** 已完成：直接身体、语义行动、视觉、说话、
   环境、生命周期场景均已运行，当前事实文档和证据已对齐。现在可以用独立治理变更
   删除本台账及注册表中的两项注册。

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

单元测试、传输 Round Trip、目录名或截图中的任意一项都不足以单独关闭缺口。现在所有行
都已带齐五类证据；本台账及其双语注册项要等独立治理变更后才删除。
