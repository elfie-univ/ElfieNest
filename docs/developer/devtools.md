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

## 数据根

三个实验台默认使用 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，并分别在
`elfie_lab/`、`nest_lab/`、`runtime_lab/` 下写入自己的配置、会话和调试数据。
它们绝不以 `${ELFIE_HOME:-~/.elfienest}` 为默认值；若把生产根显式传给 Elfie Lab
的 Runtime 配置，会被拒绝。需要运行 Runtime Lab 子进程时，也必须把它的开发根
显式作为该进程的 `ELFIE_HOME`。

本地验收可同时隔离两类数据：

```bash
ELFIE_HOME=/tmp/elfienest-production \
ELFIE_DEV_HOME=/tmp/elfienest-developer \
./developer.sh elfie-lab
```
