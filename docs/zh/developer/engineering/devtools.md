# Developer Tools

## 入口

统一入口是：

```bash
./developer.sh --help
```

实验页面由同一个 HTTP 服务承载：

| 命令 | 初始页面 | 关注点 |
| --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | 单只精灵的档案、感知、决策和回合 |
| `./developer.sh brain-eval` | `/elfie/evaluations` | Brain 批量评测与报告 |
| `./developer.sh nest-lab` | `/nest/experiment` | 固定房间、临时角色、Godot 事件与语义移动 |

资产预览使用 Nest Lab（`./developer.sh nest-lab`，`/nest/experiment`）。
独立的 `/assets/design` 页面、设计工作区和离线资产 CLI 已移除。后续资产创作使用
`godot_project/` 中现有的正式 GLB 资源、sidecar 元数据、场景和脚本；
通过 Nest Lab 预览这些正式资源的变化。

「地形与铺装」源文件保存连续地形和铺装；「石头共享库」保存景观石与岸石原型。
石头的位置由总装恢复，因此单独查看地形源文件时不再显示散落石头。

「庭院 → 功能区」直接打开地面与设施、建筑区绿化、水榭和草原总装；森林保留分组，
内含森林区总装与标志大树。中央绿化原位引用共享花草库。水榭总装保存喷泉实例、
粒子、计时器和动态材质，引用唯一的喷泉 GLB。

单件资产预览中，按住鼠标左键拖动旋转，按住右键拖动平移，滚轮缩放。
「复位」会恢复资产中心和初始视角。

整体场景的机位与复位在渲染器发布视角目录后即可使用；人物动作仍要求 Runtime 配置就绪。

正式运行、整体预览和导出统一读取 `nest/assembly/estate.tscn`。
`activity_regions.tres` 保存活动权限，`runtime-bindings.json` 保存逐摆位语义与灯光控制。
通过受控 Godot 主机入口运行 `tools/bake_estate_spatial.gd`，完整碰撞、导航、活动掩码、
交互和门控快照会输出到 `build/estate_spatial/`。验证后同步其中的 `estate_spatial.res`
与 `runtime-inputs.json` 到正式资源路径。Web 与 Linux Dedicated 导出都核对同一份输入哈希，
拒绝使用陈旧空间数据；authority 包从同一导出中移除显示资源。
`tools/export_split_activity.gd` 仅单独导出活动输入，不替代完整烘焙。

它们可以复用底层库和同一份 Godot Web Runtime，但不能依赖普通用户鉴权、
`ElfieNestEngine` 或生产数据才能启动。启动实验页面时会自动检查该
Runtime；只有缺失或 Godot 源码发生变化时才重新导出。

Elfie Lab 与 Nest Lab 的浏览器壳共用 `devtools/web/` 的 React + TypeScript + Vite 工程。
前端产物只生成到 `build/components/devtools-web/`，不会写回或提交到源码目录；启动命令会
按前端源码摘要自动复用或重建它。Nest Lab 的相机按钮只发送总览、活动区、宿舍、传送室和
还原视角这些受限意图，Godot 仍是相机变换的唯一事实源。

Nest Lab 在浏览器中嵌入已导出的固定房间，固定提供 32 个床位。开发者可添加 Saevi/Tovren、开启
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

## 资产合并原则

家具、房间和完整建筑均按以下原则处理：

- 按独立功能、运动和显隐边界分组，不按颜色或制作细节分组。始终一起使用的静态
  部件可以合并；门、抽屉、可独立控制的灯光、建筑模块和楼层显隐边界分别保留。
- 床体、床垫、被子和每只枕头分别独立。包边、缝线和固定装饰归入所属物件。
- 不同颜色与表面质感可通过顶点颜色和 PBR 贴图图集合到一个网格中。保留颜色、
  粗糙度、金属度、法线、发光、纹理重复和边缘留白，不默认把全部表面改成同一种材质。
- 分别统计功能部件、网格对象、材质图元和三角面。仅放进同一个父组，或把多个材质
  放进一个网格，并不会自动减少绘制批次。透射或透明效果可能仍需独立绘制。
- 先优化组，再按另行确认的范围减面。保留坐标、尺寸、法线、拓扑、动画部件归属和
  查看器使用的标签。
- 保留已确认基准，生成新的本地版本。验证几何、材质贴图映射和独立部件，再在现有
  Nest Lab 中用相同视角与光照比较新旧效果。
- 在资产验证产物中记录实测数量、外观变化和贴图显存成本。绘制批次减少不能单独
  证明拖动交互已经加速。

## 数据根

共享交互服务默认使用 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，并分别在
`elfie_lab/`、`nest_lab/` 下写入自己的配置、会话和调试数据。它绝不以
`${ELFIE_HOME:-~/.elfienest}` 为默认值；若把生产根显式传给 Elfie Lab 的 Runtime
配置，会被拒绝。

Brain Eval 的显式产物动作会为捕获创建一次性 Runtime 状态，且只把可再生成产物写入
`build/brain-eval/<run-id>/`。它会拒绝生产 `ELFIE_HOME` 和该构建树之外的输出路径。
设计原理和批量操作分别见
[Elfie Brain 评价与进化系统](../designs/elfie/brain/elfie-brain-evaluation-system)与
[Brain 评价工作流](./brain-evaluation)。

本地验收可同时隔离两类数据：

```bash
ELFIE_HOME=/tmp/elfienest-production \
ELFIE_DEV_HOME=/tmp/elfienest-developer \
./developer.sh brain-eval
```
