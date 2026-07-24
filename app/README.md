# App 模块

## 模块定位

`app/` 是 ElfieNest 的产品应用层：承接用户用例和入站接口，组合基础设施，
并在需要跨越 `elfie/`、`nest/` 与 `ai_runtime/` 时负责应用级编排。

## 负责与不负责

负责：

- 账户、领养、配置、初始化等产品用例；
- HTTP、Web、CLI 等入站接口；
- 数据库、文件系统和设备能力等产品基础设施适配；
- 真实精灵、Nest、AI Runtime 与 Godot 通道之间的跨模块流程；
- 桌面服务进程的应用级生命周期编排。

不负责：

- 在应用层重新实现单精灵的大脑、身体、记忆或通信；
- 在应用层保存 Nest 几何、坐标或 Godot 场景事实；
- 在 `features/` 或 `interfaces/` 中直接实现模型供应商和工具运行时；
- 在 `bootstrap/` 中放业务规则。`bootstrap/` 只允许创建对象、注入依赖和完成
  组合根装配。

## 目录地图

```text
app/
├── bootstrap/       # 应用组合根，只做依赖装配
├── features/        # accounts、adoption、configuration、setup 等产品用例
├── infrastructure/  # persistence、filesystem、devices 等适配器
├── interfaces/      # api、cli、web 入站接口
└── orchestration/   # 跨 Elfie、Nest、AI Runtime 和平台的流程编排
```

## 公开入口

- `app.interfaces.api.create_app`：创建 HTTP/Web 应用；
- `app.orchestration.ElfieNestEngine`：推进 Nest 环境时钟并泵送类型化输入；
- `app.orchestration.NestSession`：真实 `Elfie` 实例与 `Nest` 的唯一组合位置。
- `app.orchestration.embodiment`：以持久化 lease 编排真实身体绑定、托管与归巢；
  `nest/embodiment` 仅保存状态，不保存真实精灵或设备连接。
- `app.infrastructure.devices.DeviceGatewayTransport`：将已认证的局域网设备接入
  `elfie.body.external.ExternalTransport` 契约；设备事件、动作轮询和回执不进入 Nest。

`NestSession` 持有真实精灵对象，Nest 只接收精灵 ID 和巢内状态；其他模块不得另建
一套精灵与活动空间的组合关系。

## 依赖方向

```text
interfaces ──> features / orchestration
features   ──> infrastructure + 各领域公开 API
orchestration ──> elfie + nest + ai_runtime
bootstrap  ──> 以上模块（仅装配）
```

跨 `elfie/`、`nest/` 和 `ai_runtime/` 的产品流程进入 `app/orchestration/`。
下层模块不得为了调用产品功能而反向导入 `app.interfaces`。

## 运行与调试

从仓库根目录运行应用层重点检查：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q test/app/

UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q \
  test/app/orchestration/test_engine.py \
  test/app/orchestration/test_engine_cognitive_loop.py
```

完整环境准备、统一质量门和产品启动方式见
[`CONTRIBUTING.md`](../CONTRIBUTING.md)；当前整体边界见
[`docs/developer/`](../docs/developer/)。

## 对应测试

- `test/app/features/`：产品用例；
- `test/app/infrastructure/`：持久化等基础设施；
- `test/app/interfaces/`：API、CLI 和 Web 边界；
- `test/app/orchestration/`：引擎、认知循环和平台生命周期；
- `test/architecture/test_project_structure.py`：顶层目录、旧包与质量门契约。
