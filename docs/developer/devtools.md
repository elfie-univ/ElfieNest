# Developer Tools

## 入口

统一入口是：

```bash
./developer.sh --help
```

工具分为三个相互隔离的工作台：

| 工具 | 入口 | 关注点 |
| --- | --- | --- |
| Elfie Lab | `./developer.sh elfie-lab` | 单只精灵的档案、感知、决策和回合 |
| Nest Lab | `./developer.sh nest-lab` | 巢、环境时间、房间语义和事件传播 |
| Runtime Lab | `./developer.sh runtime-lab` | Provider、模型、粮食、工具和安全 |

它们可以复用视觉变量和底层库，但不能依赖普通用户鉴权、Godot 正式产品入口或生产
数据才能启动。
