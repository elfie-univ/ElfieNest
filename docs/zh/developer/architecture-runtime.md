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
`${ELFIE_HOME:-~/.elfienest}/runtime.json`。

权威宿主由 `godot_runtime/` 选择，不携带 Nest 状态、场景数据或协议凭据：

| 宿主类型 | 显示模式 | 用途 |
| --- | --- | --- |
| `web_authority` | 图形化 | 已导出的 Godot Web 权威 |
| `electron_authority` | 图形化 | 用于已导出 Web 权威的独立 Electron 权威角色 |
| `linux_dedicated` | 无显示 | Linux x64 已导出的 Dedicated 权威 |

`godot_project/` 仍是可编辑的源工程。Supervisor 承载的是已导出的 Runtime 产物；
Python 与 Desktop UI 都不会把 Godot 源资产当作 Runtime 依赖读取。

## Owner lease 与 Desktop 挂接

完整健康后，Supervisor 会记录含 `owner_id` 与 Runtime generation 的 owner lease。
发现健康 Runtime 的客户端只会挂接并取得 generation，不获得停止权；启动该 generation
的客户端才获得 lease，并且只能停止同一个 lease。这样一个仅观察的 Desktop 窗口不能
停止它没有创建的 Runtime。

Electron Observer 位于 `app/interfaces/desktop/`，不在已移除的顶层 `desktop/` 目录。
它的公开 lifecycle client 调用用户可见的 CLI 命令，绝不导入 Supervisor 内部实现、
Godot Gateway 协议帧或权威凭据。关闭 Observer 窗口没有生命周期副作用；只有客户端
持有 owner lease 时，显式退出应用才会停止 Runtime。

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

`/monitor` 是仅 Owner 可访问的完整观察页面。Owner 的精灵巢管理弹窗嵌入同一个
`ObservationMonitor` 表面与 bridge，而不是实现另一套相机能力。

封闭的本地导航 intent 是 `request_resync`、`focus_room` 与 `focus_elfie`。唯一会改变
世界的请求是单独授权、限流的高层 `request_interaction`（`greet` 或 `rest`），它经由
应用边界送到 world sink。第一阶段的 Observer 不是相机/视频传输：不发送 JPEG 帧，也
不提供相机流 API。

## Runtime 产物契约

产物清单只接受四个原生 target：`darwin-arm64`、`darwin-x64`、`win32-x64` 与
`linux-x64`。每个 target 都有 `godot-web` Observer 组件和 `desktop-observer` 组件；
只有 `linux-x64` 额外拥有无显示的 `linux-dedicated` 权威组件。清单验证组件模式、入口、
文件哈希与 target 适用范围。这是产物契约，不表示任何具体安装包已构建或已安装。

## 数据目录

| 类型 | 位置 | 是否提交 |
| --- | --- | --- |
| 用户配置、数据库、精灵档案、本地密钥和 Runtime 收据 | `${ELFIE_HOME:-~/.elfienest}` | 否 |
| 可再生中间产物 | `build/` | 否 |
| 最终发行物 | `dist/` | 否 |
| 公开文档源 | `docs/` | 是 |

## 生产目录契约

一台电脑只有一个生产 Nest 根 `${ELFIE_HOME:-~/.elfienest}`。根目录保存 Nest 级别
事实，例如 `nest.db`、备份、Runtime 状态与日志。正式 Runtime 配置按职责拆分到
`configs/` 下的 `runtime.yaml`、`providers.yaml`、`tools.yaml` 和
`food-packages.yaml`。API Key 和结构化 OAuth 凭据位于
`configs/credentials/`。`nest.db` 只保存账号、权限、精灵登记/归属、Nest 世界与
运行状态；它不接收新的聊天消息。

Runtime 调用方仍看到一份合并配置对象。存储边界在读取时合并 Runtime、Provider 和
Tool 三份文件，在写入时再次按职责拆开；这是内部持久化细节，不改变 Owner API 的
数据形状。`reports/` 预留给可重建的验证结果。这些目录及其敏感子目录都以仅所有者
可访问的权限创建。程序不会读取或隐式迁移旧根目录下的 `config.yaml`、`foods.yaml`
和 `food_history/`。显式传入 `config_home` 的开发 Runtime Lab 继续使用彼此隔离的
`config.yaml`、`.env`、`foods.yaml` 与 `food_history/`。

系统支持的 Provider 元数据使用另一份带版本的目录。内置
`ai_runtime/providers/provider-catalog.yaml` 是离线基线，并会进入 wheel 与冻结
可执行文件。完整且通过 schema 校验的 `configs/provider-catalog.yaml` 会在下次
进程启动时覆盖内置基线；版本不兼容、档案损坏或包含凭据字段的目录会被拒绝，程序
继续使用内置基线。当前尚未实现远程目录下载器，这个覆盖路径只是为后续更新机制
保留的落盘边界。`configs/providers.yaml` 仍只保存用户实际配置的 Provider 实例，
不能与元数据目录混为一谈。

Provider 配置把“已配置”“模型发现”和“已验证”作为三类独立事实。保存 Key 或
endpoint 只会标记为已配置。模型发现会记录来源、时间和结果；拉取失败或返回空列表
时绝不会覆盖用户手工填写的模型。随后由显式的单个验证或有并发上限的批量验证记录
连通状态与时延。当前状态保存在 `configs/providers.yaml` 里供快速投影，每一次经过
脱敏的验证也会写入
`reports/provider-validations/<provider_id>/latest.yaml` 和不可变的
`history/` 记录。模型测速在 `reports/model-validations/` 下采用相同的
latest 加 history 方式；模型目录使用不透明哈希，模型 ID 不会直接成为路径。

Owner API 提供面向提醒的 Provider 健康摘要。验证通过但超过 24 小时的结果会标记为
`stale`；失败、过期和从未验证的已配置 Provider 都需要提醒。这里是读取时投影，不是
后台调度器。当前阶段支持显式单个验证和有上限的批量验证；后续定时调度必须由 Runtime
生命周期统一持有，不能让 API 或 Desktop 进程自行创建新的生命周期所有者。

粮食套餐是带版本的 YAML 配置，不是由数据库持有的模型定义。每个自定义套餐会取得
不透明且不可变的 `food_<hex>` key；显示名称和角色模型可以修改，外部引用不会随之
变化。一个套餐可以配置主模型、深度推理模型、视觉模型、校验模型和技术模型回退。
落盘的执行档位中不再保存工具权限：工具由 Runtime 策略启用，再由调用它的精灵或请求
收窄，与模型选择相互独立。

目录记录一个全局默认套餐和一个可选的全局保底套餐。保底套餐允许使用远程模型，但
Owner API 会给出警告，因为它无法覆盖断网情况。只有所有已配置角色都使用声明为本地的
Provider 时，套餐的 `local_only` 才为 true。迁移阶段仍保留内置语义配方作为自动生成
模板，但正式落盘目录和 Owner 编辑器已经允许任意稳定套餐 ID。

套餐内容和分配关系由不同事实源持有。YAML 仍是模型角色与参数的唯一事实源；
`nest.db.food_package_access` 只保存每个用户可选择的稳定套餐 ID，
`nest.db.elfie_food_preferences` 只保存每只精灵最多一个主粮套餐 ID。全局默认粮和
保底粮始终进入有效可用范围。精灵保存的选择如果超出范围，或者对应 YAML 套餐已经
缺失，投影会回到全局默认粮，同时保留数据库中的原 ID 供诊断。只要仍有用户或精灵
引用某个套餐，删除操作就会被拒绝。

应用编排层会在每次生成时解析该精灵当前生效的套餐，只把稳定套餐 ID 注入
Brain 到 Runtime 的适配器。Brain 不导入数据库、Provider 目录或粮食领域模型。
任务差异始终在所选套餐内部处理：复杂请求可以使用该套餐的深度推理角色，多模态请求
可以使用视觉角色，技术回退仍限定在同一套餐内。只有所选套餐的所有候选模型都失败时，
Runtime 才会再尝试一次目录中的全局保底粮。结构化生成进入保底粮时会降为普通 JSON
文本模式，避免把本地或能力较弱的保底模型误判为支持原生 Schema。套餐关系按每次生成
动态解析，因此 Owner 修改主粮后无需重建精灵即可生效。

每只精灵都以不可变的 `elfie_id` 作为工作区名。显示名称可改，但绝不能改动目录：

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # Nest、账号、归属和世界状态
├── configs/
│   ├── runtime.yaml                # 系统设置与 Runtime 策略
│   ├── providers.yaml              # Provider 实例与模型配置
│   ├── provider-catalog.yaml        # 可选、经校验的完整元数据覆盖包
│   ├── tools.yaml                  # 工具设置，不含明文密钥
│   ├── food-packages.yaml          # 当前生效的粮食套餐目录
│   ├── food-packages-history/      # 粮食套餐历史版本
│   └── credentials/
│       ├── api-keys.env            # Provider 与工具 API Key
│       └── oauth/
│           └── <provider_id>.json  # 结构化、可刷新的 OAuth 凭据
├── reports/
│   ├── provider-validations/       # 脱敏的 Provider latest 与 history
│   ├── model-validations/          # 脱敏的模型测速 latest 与 history
│   └── runtime-validations/        # 预留的 Runtime 整体报告
├── runtime.json                    # Supervisor 健康、generation 与 owner lease
└── elfies/
    └── <elfie_id>/                 # 稳定 ID，不使用可变名称
        ├── profile.yaml 等档案、记忆和工作内容
        └── conversations/
            └── history.sqlite      # 该精灵的所有本机渠道聊天
```

`history.sqlite` 记录会话、渠道、发送方、用户关系、文本、元数据和附件引用。不会建立
用户视角的本机聊天副本，也不会把附件二进制塞进数据库。网页、桌面、微信或飞书等
渠道都按所属精灵写入这一个工作区。

## 开发与安装路径

只有一条源码开发路径：在 checkout 中运行 `./elfienest.sh`；它会先检查锁定的开发
环境，再进入产品菜单。它不是安装方式。

正式安装方式恰好有三种：面向当前原生 target 的源码安装 `./install.sh`；取得匹配平台
原生安装包后手动安装；以及在公开 endpoint 发布后使用远程校验 bootstrap。第三种当前
没有公开下载命令。这三种方式会收敛到同一产物契约；本页不声称目前存在可用产物。

## 开发边界

Developer Tools 默认使用独立根 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，其下的
`elfie_lab/`、`nest_lab/`、`runtime_lab/` 不得回退读取生产根。测试应同时设置临时
`ELFIE_HOME` 与 `ELFIE_DEV_HOME`。

`nest.db.chat_messages` 是未发布阶段遗留的废弃表。数据库升级会直接删除它；不提供
兼容读取、复制或迁移工具。新聊天只能位于对应精灵工作区。

## 内部契约

Pydantic 模型是内部数据结构的唯一事实源。代码需要时可以运行时调用
`model_json_schema()`；仓库不维护第二份 JSON Schema 文件。
