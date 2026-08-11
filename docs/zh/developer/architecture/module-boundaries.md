# 模块边界

> 本文描述当前可运行边界。规范性目标只由[系统契约](../contracts/system)和
> [应用契约](../contracts/application)定义；已知偏差记录在
> [一致性台账](../conformance/)中。

## 根模块职责

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| `elfie/` | 个体档案、大脑、身体、神经系统、通信和技能 | 账户、Nest、Runtime 生命周期 |
| `nest/` | 巢内语义状态、环境时间和互动传播 | 创建或持有 `ElfieIndividual`、房屋几何或权威宿主 |
| `infrastructure/godot/gateway/` | Python 侧已认证 Godot 传输、协议帧、Session 与 Bundle 检查 | Nest 世界语义、产品授权或进程生命周期 |
| `app/orchestration/lifecycle/` | Runtime 生命周期、完整健康、owner lease 与权威启停 | 产品 UI、账户规则和原始场景事实 |
| `godot_runtime/` | 权威宿主选择、产物元数据和已导出 Runtime 启动 | Nest 业务状态、场景编辑或产品路由 |
| `app/interfaces/desktop/` | Electron Observer 窗口、平台集成和公开 lifecycle client | Supervisor、Gateway 内部实现、权威凭据和产品规则 |
| `app/` | 产品用例、接口、基础设施和跨模块编排 | 取代领域模块的内部状态 |
| `ai_runtime/` | Provider、模型、策略、工具、安全和推理 | 账户与 Nest 业务规则 |
| `godot_project/` | 房屋、坐标、移动、碰撞、角色和渲染源码 | Python 侧业务状态或 Runtime 生命周期 |
| `devtools/` | 隔离的开发和调试入口 | 普通用户产品导航 |

## 组合、权威与观察

真实 Elfie 与 Nest 只在 `app/orchestration/NestSession` 组合。
`app/orchestration/lifecycle` 是启动、停止或重启 Core、Gateway 与选中 Godot 权威
的唯一权威。Gateway 把高层语义命令送往 Godot，并回收已经发生的物理事实；Python
不会重建导航、碰撞、坐标或渲染。

Observer 是面向产品、已认证的语义投影。它只能读取被授权的房间或归属自己的 Elfie
范围，并且只能发送[运行时与数据](./runtime)中记录的封闭高层 intent。
它不是第二个权威，也不是 Godot 协议帧的转发通道。

## 依赖方向

```text
app/bootstrap → app/orchestration → elfie / nest / ai_runtime
app/orchestration → infrastructure/godot/gateway → 已导出 Godot 权威
app/orchestration/lifecycle → godot_runtime → 已导出 Godot 权威
app/interfaces/desktop → 公开 lifecycle CLI 与已认证 Observer 表面
app/interfaces → app/features
app/infrastructure → Feature / Orchestration Port
app/bootstrap → interfaces + features + orchestration + infrastructure
```

底层模块不反向依赖 `app.interfaces`。Interface、Feature 和 Infrastructure 只能使用
公开的 Observer/Gateway 读取表面，不能构造权威宿主或发送原始 Runtime 帧。任何跨边界
变更都必须同步更新架构测试及英文和简体中文文档。Feature 不导入具体
Infrastructure；运行时调用只能通过注入的、由消费方定义的 Port 到达 Adapter。规范性
细节见[应用架构契约](../contracts/application)。
