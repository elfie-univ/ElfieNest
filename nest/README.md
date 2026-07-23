# Nest 模块

## 模块定位

`nest/` 实现精灵活动空间的 Python 领域模型：维护居民 ID、巢内语义状态、环境时钟
和互动传播，并提供与 Godot Runtime 连接所需的协议适配。

## 负责与不负责

负责：

- 居民注册、移除、姿态、目标家具和活动状态；
- 环境时间推进、说话传播、碰撞和触觉等巢内互动；
- Godot WebSocket 事件白名单、会话适配和已导出 Runtime 的发现；
- 维护 Godot 连接与 Web 构建产物的检查结果。

不负责：

- 创建、恢复或持有真实 `Elfie` / `ElfieIndividual` 对象；
- 执行单精灵认知、记忆、身体或通信生命周期；
- 定义房屋几何、世界坐标、碰撞体、导航网格、家具资源和渲染；
- 编排 AI Runtime 或产品账户流程。

`NestState` 只保存精灵 ID 和巢内状态。房屋、几何、坐标、移动、碰撞判定与
渲染的唯一源码来源是 `godot/`；Python 侧只保存业务所需的语义状态和通信边界。

## 目录地图

```text
nest/
├── nest.py         # Nest 公开门面
├── state/          # 配置、居民/家具/Godot 会话状态
├── engine/         # 环境时钟推进
├── interaction/    # 说话、用户消息、碰撞与触觉传播
├── godot/          # WebSocket 协议、API、动作映射和 Runtime 适配
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
godot/ ──> 场景与几何的唯一事实源
```

`nest/` 不依赖 `app/`、`elfie/` 或 `ai_runtime/`。需要把 Nest 事件交给真实
精灵时，由 `app/orchestration/` 按 ID 查找并调用精灵对象。

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
- `test/nest/godot/`：握手、协议和 Web 构建产物；
- `test/architecture/test_project_structure.py`：Nest 目录结构与旧包禁令；
- `test/app/orchestration/`：真实精灵和 Nest 的组合行为。
