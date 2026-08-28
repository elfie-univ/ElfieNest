# Developer Tools

## 入口

统一入口是：

```bash
./developer.sh --help
```

工具提供三个页面入口，由同一个同源 HTTP 服务承载：

| 命令 | 初始页面 | 关注点 |
| --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | 单只精灵的档案、感知、决策和回合 |
| `./developer.sh brain-eval` | `/elfie/evaluations` | Brain 批量评测与报告 |
| `./developer.sh nest-lab` | `/nest/experiment` | 固定房间、临时角色、Godot 事件与语义移动 |

它们可以复用底层库和同一份 Godot Web Runtime，但不能依赖普通用户鉴权、
`ElfieNestEngine` 或生产数据才能启动。启动任一页面时会自动检查该
Runtime；只有缺失或 Godot 源码发生变化时才重新导出。

Elfie Lab 与 Nest Lab 的浏览器壳共用 `devtools/web/` 的 React + TypeScript + Vite 工程。
前端产物只生成到 `build/components/devtools-web/`，不会写回或提交到源码目录；启动命令会
按前端源码摘要自动复用或重建它。Nest Lab 的相机按钮只发送总览、活动区、宿舍、传送室和
还原视角这些受限意图，Godot 仍是相机变换的唯一事实源。

Nest Lab 在浏览器中嵌入已导出的固定房间。开发者可修改床位数、添加狐狸/小狗、开启
Python 定时选择语义锚点的随机游走，或暂停、继续、重置实验。Godot 负责几何、渲染、
路径与碰撞；Lab 只发送 v2 语义命令并记录 Runtime 事实。两种 Lab 都使用与正式桌面
运行相同的 Godot Web 导出物；只是各自提供隔离的网页外壳、数据根和本地协议入口。

本机端口固定分层：正式 App 为 `8000` / `8765`，三个页面入口共享 HTTP
`127.0.0.1:9001`；Nest 页面的 Godot WebSocket 是内部 `9002` 监听，不是第二个网页。
直接使用任一默认命令会安全重启当前工作区共享服务；只有显式传入端口时才保留并行实例，
且未知端口占用者不会被终止。

Elfie Lab 首次启动直接读取隔离 Runtime `nest.db` 中的粮食目录。数据库会初始化两
个系统粮食，它们在页面配置 Ollama 或 OpenAI 兼容 Provider 前显示为未配置；页面不会
注入额外的模拟粮食行。配置表单只保存选择的模型和连接，第一次真实回合才会尝试连接模型。

## 数据根

共享交互服务默认使用 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，并分别在
`elfie_lab/`、`nest_lab/` 下写入自己的配置、会话和调试数据。它绝不以
`${ELFIE_HOME:-~/.elfienest}` 为默认值；若把生产根显式传给 Elfie Lab 的 Runtime
配置，会被拒绝。

Brain Eval 的显式产物动作会为捕获创建一次性 Runtime 状态，且只把可再生成产物写入
`build/brain-eval/<run-id>/`。它会拒绝生产 `ELFIE_HOME` 和该构建树之外的输出路径。
设计原理和批量操作分别见
[Elfie Brain 评价与进化系统](../designs/elfie-brain-evaluation-system)与
[Brain 评价工作流](./brain-evaluation)。

本地验收可同时隔离两类数据：

```bash
ELFIE_HOME=/tmp/elfienest-production \
ELFIE_DEV_HOME=/tmp/elfienest-developer \
./developer.sh brain-eval
```
