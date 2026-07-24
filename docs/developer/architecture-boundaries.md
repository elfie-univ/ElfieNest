# 模块边界

## 根模块职责

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| `elfie/` | 个体档案、大脑、身体、神经系统、通信和技能 | 账户、Nest、桌面生命周期 |
| `nest/` | 巢内状态、环境时间、互动传播、Godot 语义协议 | 创建或持有 `ElfieIndividual`、房屋几何 |
| `app/` | 产品用例、接口、基础设施、跨模块编排 | 取代领域模块的内部状态 |
| `ai_runtime/` | Provider、模型、策略、工具、安全和推理 | 账户与 Nest 业务规则 |
| `desktop/` | Electron 窗口、平台资源和进程监督 | Elfie 认知、领养和聊天规则 |
| `godot/` | 房屋、坐标、移动、碰撞、角色和渲染 | Python 侧业务状态 |
| `devtools/` | 隔离的开发和调试入口 | 普通用户产品导航 |

## 唯一组合位置

真实 Elfie 与 Nest 只在 `app/orchestration/NestSession` 组合。这样 `Nest` 可以保持
纯粹的巢内语义，`Elfie` 可以作为独立个体测试，应用层负责把它们装配成产品会话。

## 依赖方向

```text
app/bootstrap → app/orchestration → elfie / nest / ai_runtime
app/interfaces → app/features → app/infrastructure
desktop → Python Core / Godot Web Runtime
```

底层模块不反向依赖 `app.interfaces`；跨边界变更必须同步架构测试和对应 README。
