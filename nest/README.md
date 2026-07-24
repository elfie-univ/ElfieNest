# Nest 模块

## 模块定位

`nest/` 实现精灵活动空间的 Python 领域模型：维护居民 ID、巢内语义状态、环境时钟
和互动传播，并提供与 Godot Runtime 连接所需的协议适配。

## 负责与不负责

负责：

- 居民注册、移除、长期床位分配、姿态和活动状态；
- 环境时间推进、说话传播、碰撞和触觉等巢内互动；
- Godot Runtime v2 的鉴权、单权威会话、命令/事件队列和速率限制；
- 场景语义目录、Runtime 临时镜像和已导出 Web Runtime 的完整性检查。

不负责：

- 创建、恢复或持有真实 `Elfie` / `ElfieIndividual` 对象；
- 执行单精灵认知、记忆、身体或通信生命周期；
- 定义房屋几何、世界坐标、碰撞体、导航网格、家具资源和渲染；
- 编排 AI Runtime 或产品账户流程。

`NestState` 只保存精灵 ID、长期住处和巢内语义状态，不保存家具副本、坐标或
真实精灵对象。房屋、几何、坐标、移动、碰撞判定与渲染的唯一源码来源是独立
Godot 源工程 `godot_project/`；Python 侧只保存业务所需的语义状态和通信边界。

## 目录地图

```text
nest/
├── nest.py         # Nest 公开门面
├── state/          # 配置、居民、住处、世界目录与 Runtime 镜像
├── engine/         # 环境时钟推进
├── interaction/    # 说话、用户消息、碰撞与触觉传播
├── godot/          # v2 消息、权威会话、WebSocket 网关与 Runtime 产物检查
└── events.py       # Nest 领域事件值对象
```

## 公开入口

- `nest.Nest`：组合状态、环境时钟和互动传播；
- `nest.NestConfig`：Nest 容量等配置；
- `nest.NestFullError`：居民容量已满错误；
- `nest.NestState`：仅包含巢内状态的运行容器；
- `nest.godot.GodotAPIServer`：Python 与 Godot Runtime 的 WebSocket 边界。

真实精灵注册由 `app.orchestration.NestSession` 完成；不要把真实对象塞入
`NestState`。

## 依赖方向

```text
app/orchestration ──> nest
nest.nest ──> state + engine + interaction
nest.godot ──> Nest/Godot 边界
godot_project/ ──> 场景与几何的唯一事实源
```

`nest/` 不依赖 `app/`、`elfie/` 或 `ai_runtime/`。需要把 Nest 事件交给真实
精灵时，由 `app/orchestration/` 按 ID 查找并调用精灵对象。

## Runtime v2 生命周期

Godot Runtime 连接后必须先发送带随机 nonce、`runtime_id` 和 `protocol: 2`
的 `hello`。同一时刻只有一个 Runtime 拥有权威；新一代连接会获得递增
`generation`，旧代事件不会进入 Nest。

启动同步按固定顺序收敛：

1. 编排层发送 `configure_world`，包含 `nest_id`、床位数和世界 revision；
2. Runtime 构建房间与导航，回传不含坐标的 `scene_manifest`；
3. Runtime 回传 `world_ready`，Python 才发送完整 `sync_actors`；
4. Runtime 回传 `world_snapshot`，Nest 只保存临时语义镜像。

身体动作使用有生命周期的语义命令，而不是由大脑逐帧发“走一步”。例如
`execute_intent(intent="move_to_anchor")` 交给 Godot 按导航网格逐物理帧执行；只有接受、开始、完成、阻塞、
取消、超时、触觉接触和说话听众等关键事实回传 Python。Runtime 断线或 generation
变化时，等待中的身体命令统一进入中断状态，由精灵下一次决策处理。

## 运行与调试

从仓库根目录运行 Nest 领域和 Godot 协议检查：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q test/nest/

UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q \
  test/nest/test_nest.py \
  test/nest/godot/test_api_handshake.py
```

如需打开、运行或截图 Godot 项目，必须先遵守仓库的 Godot 操作门；这里的测试不
需要启动 Godot 编辑器。开发环境与统一质量门见
[`CONTRIBUTING.md`](../CONTRIBUTING.md)。

## 对应测试

- `test/nest/test_nest.py`：状态、环境时钟和互动传播；
- `test/nest/godot/`：v2 握手、消息校验、权威会话和 Web 构建产物；
- `test/e2e/test_nest_runtime_v2.py`：重连后的世界与完整角色目录收敛；
- `test/architecture/test_project_structure.py`：Nest 目录结构与旧包禁令；
- `test/app/orchestration/`：真实精灵和 Nest 的组合行为。
