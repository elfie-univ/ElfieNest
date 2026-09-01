# Nest 模块

> 中文版：本文件 · [English](README.md)

## 模块定位

`nest/` 实现精灵活动空间的 Python 领域模型：维护居民 ID、巢内语义状态、环境时钟
和互动传播。Godot 传输与协议适配器位于领域外的
`infrastructure/godot/`。

## 负责与不负责

负责：

- 居民注册、移除、长期床位分配、姿态和活动状态；
- 环境时间推进和期望环境规则；
- 说话、视觉和语义行动的短期关联，以及一套类型化 Nest 事件 Outbox；
- 场景语义目录和 Runtime 临时语义镜像；
- 类型化世界事实进入 NestSession 后的巢内规则处理。

不负责：

- 创建、恢复或持有真实 `Elfie` / `ElfieIndividual` 对象；
- 执行单精灵认知、记忆、身体或通信生命周期；
- 定义房屋几何、世界坐标、碰撞体、导航网格、家具资源和渲染；
- 编排跨 authority 运行流程或产品账户流程。

`Nest` Facade 组合四个所有者状态，并对外提供类型化用例。它不保存家具副本、坐标或
真实精灵对象。房屋、几何、坐标、移动、碰撞判定与渲染的唯一源码来源是独立 Godot
源工程 `godot_project/`；Python 侧只保存业务所需的语义状态和类型化通信边界。

## 目录地图

```text
nest/
├── nest.py             # Nest 稳定 Facade 与聚合装配
├── config.py           # 聚合配置
├── snapshot.py         # 技术无关的持久语义快照
├── space_facilities/   # 无坐标目录和环境事实
├── living_rules/       # 居民、Home、访问和受众规则
├── time_environment/   # 时钟、阶段、定时规则和期望状态
├── elfie_interaction/  # 说话、视觉和语义行动关联
└── events.py           # 横贯所有者的类型化事件值对象
```

## 公开入口

- `nest.Nest`：唯一 Nest 聚合 Facade；
- `nest.NestConfig`：Nest 容量等配置；
- `nest.NestSnapshot`：App 状态存储接受的持久语义形状；
- `app.orchestration.nest_session`：组合 Nest、真实精灵与类型化世界通道；
- `infrastructure.godot.gateway`：拥有具体 WebSocket 协议实现。

真实精灵注册由 `app.orchestration.NestSession` 完成；不要把真实对象塞入 Nest 聚合。

## 依赖方向

```text
app/orchestration ──> nest
nest.nest ──> 四个所有者包 + events
app/orchestration/nest_session ──> 类型化 Nest 世界边界
infrastructure/godot ──> 协议、宿主与产物适配器
godot_project/ ──> 场景与几何的唯一事实源
```

`nest/` 不依赖 `app/`、`elfie/` 或模型、Food、工具 Adapter。需要把 Nest 事件交给真实
精灵时，由 `app/orchestration/` 按 ID 查找并调用精灵对象。

## Runtime 权威与 Observer 生命周期

Godot 权威连接后完成由 `infrastructure/godot/gateway` 拥有的认证握手。同一时刻只有
一个 Runtime 拥有权威；新一代连接会获得递增 `generation`，旧代事件不会进入 Nest。
Runtime 生命周期选择已导出的宿主；`nest/` 从不启动 Godot，也不拥有宿主进程。

启动同步按固定顺序收敛：

1. 编排层发送 `configure_world`，包含 `nest_id`、床位数和世界 revision；
2. Runtime 构建房间与导航，回传不含坐标的 `scene_manifest`；
3. Runtime 回传 `world_configured`，且明确房间配置与导航均已就绪后，Python 才发送完整 `sync_actors`；
4. Runtime 回传 `world_snapshot`，Nest 只保存临时语义镜像。

身体动作使用有生命周期的语义命令，而不是由大脑逐帧发“走一步”。例如
`execute_intent(intent="move_to_anchor")` 交给 Godot 按导航网格逐物理帧执行；只有接受、开始、完成、阻塞、
取消、超时、触觉接触和说话听众等关键事实回传 Python。Runtime 断线或 generation
变化时，等待中的身体命令统一进入中断状态，由精灵下一次决策处理。

已认证的产品客户端使用独立 Observer 表面。capability 与产品会话绑定，并收窄到一个
房间或归属自己的 Elfie；它只暴露 generation/sequence 语义帧。Observer 导航只限于
resync 与 focus intent，单独授权的高层 interaction 请求会被限流。它没有几何、相机/
视频帧或权威凭据访问权。

## 运行与调试

从仓库根目录运行 Nest 领域和 Godot 协议检查：

```bash
uv run --no-sync pytest -q test/nest/

uv run --no-sync pytest -q \
  test/nest/test_nest.py \
  test/infrastructure/godot/gateway/test_api_handshake.py
```

如需打开、运行或截图 Godot 项目，必须先遵守仓库的 Godot 操作门；这里的测试不
需要启动 Godot 编辑器。开发环境与统一质量门见
[`CONTRIBUTING_zh.md`](../CONTRIBUTING_zh.md)。

## 对应测试

- `test/nest/test_nest.py`：状态、环境时钟和互动传播；
- `test/infrastructure/godot/gateway/`：权威握手、消息校验与权威会话；
- `test/app/orchestration/observer/`：具备能力范围的 Observer 投影及
  generation/sequence 行为；
- `test/infrastructure/godot/`：宿主选择、启动、产物元数据与协议传输；
- `test/e2e/test_nest_runtime_v3.py`：重连后的世界与完整角色目录收敛；
- `test/architecture/test_project_structure.py`：Nest 目录结构与旧包禁令；
- `test/app/orchestration/`：真实精灵和 Nest 的组合行为。
