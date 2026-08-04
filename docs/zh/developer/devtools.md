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
| Nest Lab | `./developer.sh nest-lab` | 固定房间、临时角色、Godot 事件与语义移动 |
| Runtime Lab | `./developer.sh runtime-lab` | Provider、模型、粮食、工具和安全 |

它们可以复用底层库和同一份 Godot Web Runtime，但不能依赖普通用户鉴权、
`ElfieNestEngine` 或生产数据才能启动。启动 Elfie Lab 或 Nest Lab 时会自动检查该
Runtime；只有缺失或 Godot 源码发生变化时才重新导出。

Elfie Lab 与 Nest Lab 的浏览器壳共用 `devtools/web/` 的 React + TypeScript + Vite 工程。
前端产物只生成到 `build/components/devtools-web/`，不会写回或提交到源码目录；启动命令会
按前端源码摘要自动复用或重建它。Nest Lab 的相机按钮只发送总览、活动区、宿舍、传送室和
还原视角这些受限意图，Godot 仍是相机变换的唯一事实源。

Nest Lab 在浏览器中嵌入已导出的固定房间。开发者可修改床位数、添加狐狸/小狗、开启
Python 定时选择语义锚点的随机游走，或暂停、继续、重置实验。Godot 负责几何、渲染、
路径与碰撞；Lab 只发送 v2 语义命令并记录 Runtime 事实。两种 Lab 都使用与正式桌面
运行相同的 Godot Web 导出物；只是各自提供隔离的网页外壳、数据根和本地协议入口。

本机端口固定分层：正式 App 为 `8000` / `8765` / `8766`，Elfie Lab 为 `9001`，Nest Lab
为 `9002` / `9003`，Runtime Lab 不监听网页端口。直接使用默认 Lab 命令会安全重启当前
工作区同类旧实例；只有显式传入端口时才保留并行实例，且未知端口占用者不会被终止。

Elfie Lab 首次启动直接读取隔离 Runtime `nest.db` 中的粮食目录。数据库会初始化两
个系统粮食，它们在 Ollama 或远端 Provider 配置完成前显示为未配置；页面不会注入
额外的模拟粮食行。

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
