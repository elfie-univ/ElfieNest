# 运行时与数据

## 唯一 Runtime 服务与权威

`app/orchestration/lifecycle/RuntimeSupervisor` 是一个 ElfieNest Runtime
generation 的唯一生命周期所有者。源码与已安装 CLI 的生命周期命令都经过同一边界。
它启动和停止 Python Core 及其 Gateway，再启动选中的已导出 Godot 权威宿主；它不会
打开 Godot Editor。

只有 Core、Gateway 与 Godot 权威都 ready 时 Runtime 才 ready。配置的公共 Ollama
endpoint 作为第四组件被探测：其不可用会使 Runtime 处于 `degraded`，不会替代权威，
也不会创建私有模型 sidecar。`status --json` 会报告封闭组件集（`core`、`gateway`、
`godot_authority`、`ollama`）和生命周期状态。Supervisor 将当前收据写入
`<所选数据根>/runtime/runtime.json`。

权威宿主由 `infrastructure/godot/lifecycle/` 选择，不携带 Nest 状态、场景数据或协议
凭据；已导出产物元数据与校验位于 `infrastructure/godot/artifacts/`：

| 宿主类型 | 显示模式 | 用途 |
| --- | --- | --- |
| `web_authority` | 图形化 | 已导出的 Godot Web 权威 |
| `electron_authority` | 图形化 | 由 Bootstrap Electron 宿主选择的 Infrastructure 权威 |
| `linux_dedicated` | 无显示 | Linux x64 已导出的 Dedicated 权威 |

`godot_project/` 仍是可编辑的源工程。Supervisor 承载的是已导出的 Runtime 产物；
Python 与 Desktop UI 都不会把 Godot 源资产当作 Runtime 依赖读取。

`app/bootstrap/desktop_host/` 是 Electron 组合与打包根，负责分发可见 Desktop
interface 或 Infrastructure 权威；`app/interfaces/desktop/` 不导入或打包权威实现。

## Owner lease 与 Desktop 挂接

完整健康后，Supervisor 会记录含 `owner_id` 与 Runtime generation 的 owner lease。
发现健康 Runtime 的客户端只会挂接并取得 generation，不获得停止权；启动该 generation
的客户端才获得 lease，并且只能停止同一个 lease。这样一个仅观察的 Desktop 窗口不能
停止它没有创建的 Runtime。

启动仍然是一个生命周期事务，但事务进行期间会写入临时的
`startup_owner_id` 收据。这个收据既阻止第二个客户端重复启动同一个 Runtime，也让
拥有者 Desktop 可以通过公开的 `stop --owner-id` 命令取消启动。只有 Core、Gateway 和
Godot 的完整就绪契约全部通过后，收据才会提升为普通 owner lease；在此之前不会报告
`ready`。

Electron Observer 位于 `app/interfaces/desktop/`，不在已移除的顶层 `desktop/` 目录。
它的公开 lifecycle client 调用用户可见的 CLI 命令，绝不导入 Supervisor 内部实现、
Godot Gateway 协议帧或权威凭据。它会立即创建本地启动壳，在 Core 和 Gateway ready 后
加载真正的管理页面，并在 Godot Observer ready 前禁用监控控件。关闭 Observer 窗口没有
生命周期副作用；显式退出会先隐藏界面，必要时取消正在进行的启动，再且仅在客户端持有
owner lease 时请求生命周期所有者停止 Runtime。
生命周期所有者会给隐藏 authority 和受管 Core 一个短暂的优雅退出窗口；若子进程无响应，
则只对再次核验身份的同一进程组强制停止，避免关闭无限等待。

## Observer 权限、相机目录与非视频第一阶段

Observer 从已认证的产品会话开始，获得一个与会话绑定的不透明 capability。订阅范围只能
是一个房间或一只归属自己的 Elfie；interest 只能缩小既有授权结果。帧按
generation/sequence 顺序携带语义身份和状态，不携带场景 transform、几何、相机状态、
原始 Runtime 协议帧或权威凭据。

产品 Observer 的完整、版本化相机目录由 Godot 拥有。每个严格的目录 envelope 都携带
语义 view `id` 与 `label`、`active_id`、正数 `revision` 以及
`presentation_paused`。它描述当前可选择的视角，不导出相机坐标、transform 或房间几何。
React 消费该目录后，只能发出封闭的语义命令 `overview`、`select`、`reset` 与
`set_local_presentation_paused`。`select` 只能使用当前目录中的 ID；React 既不计算，也不
发送相机位置、transform 或布局事实。

产品 bridge 只接受来自当前同源 Godot iframe、且满足严格版本化消息格式的目录。它不暴露
原始 Runtime 帧、权威凭据或模拟控制。local presentation pause 仅是 Observer 的输入/呈现
状态；它绝不能暂停 Runtime、Gateway、Core 或后端模拟。

产品 Observer 也可以接收严格的语义实体快照，用于只读呈现。每个实体只携带身份、物种、外观、
房间/区域状态、语义 `home_anchor_id` 和可空的 `action_anchor_id`，不携带坐标、transform、
导航或碰撞事实。Godot 在本地解析该 anchor，并负责角色放置与渲染。动作锚点、姿态和进行中
命令来自权威世界开始及完成动作时的快照。Observer 在相同场景中回放行走与已创作的床椅姿态；
重复或过期快照不会重启动作，本地暂停只停止显示物理。产品本地随机游走及模拟路径快照已移除，未知动作锚点不会回退成虚构的床位状态。
Nest Lab 保留隔离的 Python 调度器，通过真实语义移动指令驱动临时角色。React bridge 只接受并转发经过校验、发往当前同源 Observer iframe 的快照。

固定机位监控默认打开全园总览，只提供左键原地转头、右键水平轨道移动及滚轮缩放，不再提供操作方式选择。移动限制在机位对应楼层和区域内；视角下拉框右侧的复位恢复当前机位的默认位置、朝向与缩放，不切换观察对象。精灵视角仍提供跟随与代入，不显示复位；视角与播放操作不改变 authority 状态。

`/monitor` 是已登录用户可访问的观察页面。Owner/Admin 的精灵巢管理弹窗嵌入
同一个 `ObservationMonitor` 表面与 bridge，而不是实现另一套相机能力。

监控工具栏左侧为视角，右侧为暂停或继续，不显示竖向分隔线。普通 `/monitor` 跟随实时环境并隐藏时段预览；
打开 `/monitor?debug=1` 才显示本地光照预览，每次加载都从本地实时开始，不保存上次预览时段。
该参数不增加权限，预览不改变精灵巢时间或居民行为。移动端工具栏位于场景下方，视角操作可横向滑动，
右侧始终保留暂停或继续；调试时段预览单独占第二行。固定机位分为庭院（2）、主楼（4）、卧室（16），
卧室选项与选中后的视角带有对应建筑外墙色的小色点，房号、楼层文字和系统选中底色保持不变，
默认全园总览。第一组为“固定机位／精灵视角”左右切换按钮，高亮当前模式；固定机位下依次显示视角下拉框与复位，
精灵视角下依次显示精灵下拉框与观看方式。总览作为机位选项，不再提供独立总览按钮；切换机位恢复该机位的默认位置。
精灵选择框对普通 User 只列出本人拥有的精灵，对 Admin 与 Owner 使用受保护的管理员目录列出全部精灵；提供跟随与代入两种选择，不在场景中的精灵不可选择。后端 Observer 在房间与精灵两种范围内均将普通用户限制为本人精灵，管理员可观察全部精灵。
产品 Observer 为每位居民登记两种相机，仅显式精灵范围快照会初始聚焦该精灵；房间监控
不会自动跟随任意居民。这些相机只改变显示镜头，不改变居民移动或 authority 状态。跟随位移和避障距离变化均平滑
过渡，其他精灵不触发镜头避障缩放。跟随镜头遇到遮挡时优先选择精灵周围稳定、无遮挡的一侧，
避免直接缩进身体附近；安全距离同时考虑精灵碰撞体的高度。收到语义动作完成状态后，显示角色先沿本地导航
走到目标锚点再呈现最终姿态，不再直接瞬移到目的地。

封闭的本地导航 intent 是 `request_resync`、`focus_room` 与 `focus_elfie`。唯一会改变
世界的请求是单独授权、限流的高层 `request_interaction`（`greet` 或 `rest`），它经由
应用边界送到 world sink。第一阶段的 Observer 不是相机/视频传输：不发送 JPEG 帧，也
不提供相机流 API。

Monitor 默认自动轮播：完整80秒固定节目、4秒过渡、384秒随机节目及4秒返回过渡，每472秒循环。随机节目可按种子重放。中央有呼吸、蓄力、重拍、花束舒展、花瓣交替、
花束波浪6种动作；外围有呼吸、奇偶交替、对柱起伏、双峰波浪、逐根累积及退场、保留高度阶梯、
阶梯绕圈、重叠内喷、对向内喷、渐强内喷、穹顶展开，以及四直四斜、两斜六直、半圈直斜、
直斜轮换，共16种动作。8组搭配协调中央与外围，不独立随机乱配。
每段24秒回到持续喷水的衔接姿态，转向时分组降压；每轮打散16种动作且不紧邻重复。
方向、峰值高度、速度及四组协调配色随种子变化，外围上限4米，中央上限6米。
每股花瓣及外围喷头的高度、方向与落点独立传入现有水花和涟漪链路，水粒上限仍为2304。
同一种子和展示时间可重放相同画面，离屏返回直接采样，不补跑动画。
Monitor 地址参数 `fountain=fixed` 可切回固定节目，`fountain=random&fountain_seed=42` 可重放随机节目，`fountain=auto` 选择自动轮播。
这些参数仅影响展示，不改变权威世界状态。

保留的固定节目在9个固定喷位上播放无声的80秒展示编排。0～28秒中央8股花束由3.3米升至
约4.6米，外围低直喷逐渐变为奇偶交替；28～40秒先降压再转向，中央切换主柱，外围8股
向内拱喷，落在距中心0.75米的小圈。40～50秒主柱达到6米；50～66秒外围恢复直喷，
中央花束展开至独立的6米峰值；66～80秒舒缓回到开场。外围喷位仍距中心约4米，避开出水口。
直喷水芯呈白色、向上收窄，外侧回落碎水在下部更宽，顶部不膨大。共享GPU批次最多使用
2304颗小水粒表现喷雾及落水水花。中央主柱、外围8股和中央花束8股共17处可能的落水区，
在喷雾与水面泡沫、涟漪之间共享位置和水压，未喷水的落点不显示水花。夜间颜色跟随形态，
暖色主柱搭配冷色拱喷或花束。扩散光波抵达池壁内侧，并在水道中延续两道渐隐弧线，
不提高池沿亮度，不增加投影灯。每 250 毫秒检查相机视锥与实体遮挡，
画面外或被实体完全遮挡时停止动画更新并关闭局部灯，远景省略水珠。重新进入画面时直接
采样已经流逝的节奏；Monitor 暂停及页面后台挂起冻结展示，不改变权威世界。

## 完整精灵巢的物理与家具动作

`godot_project/nest/nest.tscn` 仍是唯一世界入口。完整资产中已有的模块、楼层与家具
元数据绑定物理碰撞和稳定交互锚点，不再使用退役程序化房间的坐标。镜像渲染节点会转换为
正手性的物理变换，视觉几何不移动。庭院复用已创作的碰撞代理，不把树叶全部用于导航烘焙。

世界就绪要求导航区域完成同步，并且发布的锚点具有通往庭院的有效路径，而不只是存在
非空导航资源。整套精灵巢固定提供 32 个床位的活动语义目录，不复制或重建整套精灵巢。

原生 Body 提供 `furniture.use`，参数只有 `anchor_id`。它通过已有认证的
`execute_intent` 命令转换为 `use_anchor`，调用方不能传入坐标或姿态。同一个命令先实际
导航到家具旁的接近点，再进入已创作的睡眠或坐姿，并保留原始 intent/body-generation
身份和唯一终态。普通 `move_to_anchor` 不会自动使用家具。家具被占用、路径不可达、
接触元数据无效或退出位置受阻都会明确失败。走开时恢复站立身体与碰撞。这些操作仍由
Godot 拥有，不增加 Python 几何模型、第二个 Gateway 或 Observer 模拟权威。

动画检查时，`use_anchor` 还支持可选的命名 `furniture_cycle`：`seat`、`sleep-back`、
`sleep-left`、`sleep-right`。它选择 Godot 自有的已创作流程，不接受变换矩阵或任意姿态。
普通 Body `furniture.use` 仍只传 `anchor_id`。流程执行、根运动、接触采样、转椅旋转、
睡姿和被子变形位于 `runtime/actor/`；家具接触点和碰撞仍属于 `nest/spatial/`。
Nest Lab 选择并观察同一个实现；完成、取消和失败沿用原命令身份与唯一终态。

## Runtime 产物契约

产物清单只接受四个原生 target：`darwin-arm64`、`darwin-x64`、`win32-x64` 与
`linux-x64`。每个 target 都有 `godot-web` Observer 组件和 `desktop-observer` 组件；
只有 `linux-x64` 额外拥有无显示的 `linux-dedicated` 权威组件。清单验证组件模式、入口、
文件哈希与 target 适用范围。这是产物契约，不表示任何具体安装包已构建或已安装。

## 数据目录

| 类型 | 位置 | 是否提交 |
| --- | --- | --- |
| 用户配置、数据库、精灵档案、本地密钥和 Runtime 收据 | 所选产品数据根 | 否 |
| 可再生中间产物 | `build/` | 否 |
| 最终发行物 | `dist/` | 否 |
| 公开文档源 | `docs/` | 是 |

## 生产目录契约

规范性目标由[服务生命周期契约](../contracts/service-lifecycle)唯一规定：安装版 App、
托盘与全局 CLI 只解析 `${ELFIE_HOME:-~/.elfienest}`，不存在第三个 remembered root；
源码 CLI 忽略调用方 `ELFIE_HOME`，只有 `start`、`serve`、`restart`、`stop` 接受
`--data-home`，其余命令使用会话上下文、对当前命令可用的
`<当前worktree>/.elfienest.local` 或经验证候选选择。全部生命周期收据与产品数据只跟随
唯一解析结果。

不存在持久化 remembered root 或 `data-home` 命令。源码交互 shell 只在本次
shell 生命周期内把目标保存在内存中；源码单次命令使用默认目录或重新校验后的候选目录。
`uninstall` 只由安装版 CLI 提供。

一台电脑只有一个生产 Nest 根 `${ELFIE_HOME:-~/.elfienest}`。`nest.db` 只包含最终
8 张 Nest 级表：用户、会话、本机安装/Setup、Nest 设置、精灵、外部身体、身体审计
和具身租约。聊天与记忆不使用根数据库。

Provider、模型、粮食、工具、凭据、报告和 Runtime 收据的所有权只由
[模型、Food 与工具行为契约](../contracts/model-food-tool-behavior) 定义。完整生产目录树以及
“每项持久化事实只能有一个类型化写入者”的规则也只在该契约中维护，本页不再复制这些
Schema。

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # 最终 8 张 Nest 级表
├── configs/                        # Runtime、鉴权和粮食配置
├── reports/                        # 模型证据与验证报告
├── assets/users/<user_id>/         # 头像与隔离的本地文件
├── runtime/                        # runtime.json 与锁
├── logs/                           # Runtime 事件与 Token 用量
└── elfies/
    └── <8位elfie_id>/               # 稳定 ID，不使用可变名称
        ├── profile/profile.yaml
        ├── assets/ godot/ skills/
        ├── conversations/history.sqlite # 最终 7 张聊天表
        └── memory/knowledge.sqlite      # 最终 9 张知识表
```

`history.sqlite` 记录会话、渠道、发送方、用户关系、文本、元数据和附件引用。不会建立
用户视角的本机聊天副本，也不会把附件二进制塞进数据库。网页、桌面、微信或飞书等
渠道都按所属精灵写入这一个工作区。

## 开发与安装路径

只有一条源码开发路径：在 checkout 中运行 `./elfienest.sh`；它会先检查锁定的开发
环境，再进入产品菜单。它不是安装方式。

最终用户只有一种安装路径：取得与平台匹配的原生安装包，并通过操作系统正常安装。
Release 下载只是该安装包的交付渠道，不是另一种安装方式。

## 开发边界

Developer Tools 默认使用独立根 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，其下的
`elfie_lab/`、`nest_lab/` 不得回退读取生产根。测试应同时设置临时
`ELFIE_HOME` 与 `ELFIE_DEV_HOME`。

应用在产生写入前就会拒绝旧数据根和旧 schema。请先备份，再重建所选数据根；不提供
兼容读取、复制、重放、双写或自动迁移。新聊天只能位于对应精灵工作区。

## 内部契约

Pydantic 模型是内部数据结构的唯一事实源。代码需要时可以运行时调用
`model_json_schema()`；仓库不维护第二份 JSON Schema 文件。
