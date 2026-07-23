# ElfieNest 目录架构

## 状态

本文件是当前仓库目录与依赖边界的正式规范。新代码、测试、构建脚本和设计文档必须以本规范为准。

## 根目录

```text
ElfieNest/
├── elfie/
├── nest/
├── ai_runtime/
├── app/
├── desktop/
├── godot/
├── devtools/
├── docs/
├── scripts/
├── test/
├── build/
└── dist/
```

源码、用户数据和生成产物必须分离：源码位于前九个目录；测试位于 `test/`；中间产物位于 `build/`；最终安装包位于 `dist/`；生产数据位于 `ELFIE_HOME`，默认目标为 `~/.elfienest/`。

## Nest

```text
nest/
├── __init__.py
├── nest.py
├── events.py
├── state/
├── engine/
├── interaction/
└── godot/
```

- `nest.py` 是 App 唯一依赖的公开门面。
- `state/` 保存 `nest_id`、配置、居民 ID、家具覆盖和 Godot 会话状态。
- `engine/` 只推进环境时间和调度，不调用 LLM，也不推进精灵自身生理状态。
- `interaction/` 传播发言、用户消息、触觉和碰撞结果。
- `godot/` 维护 Python 侧协议、连接、命令和导出物检查。
- Nest 不持有 `ElfieIndividual`，不维护房屋几何蓝图。

## App

```text
app/
├── features/
│   ├── accounts/
│   ├── adoption/
│   ├── chat/
│   ├── nest_management/
│   ├── nest_registration/
│   ├── administration/
│   ├── configuration/
│   └── setup/
├── orchestration/
├── interfaces/
│   ├── api/
│   ├── web/
│   └── cli/
├── infrastructure/
│   ├── persistence/
│   ├── filesystem/
│   └── device_identity/
└── bootstrap/
```

- 产品规则按功能进入 `features/`，不再创建顶层 `domain/` 与 `use_cases/` 双份目录。
- `orchestration/NestSession` 持有真实精灵实例和唯一 Nest，负责跨模块循环。
- `interfaces/` 只负责入站解析、鉴权、展示和调用产品功能。
- `infrastructure/` 实现持久化、文件和设备身份等出站能力。
- `bootstrap/` 是组合根，不实现账户、领养、聊天或 Nest 规则。

## Elfie

`elfie/` 的稳定职责目录是 `profile/`、`brain/`、`nervous_system/`、`body/`、
`communication/` 和 `skills/`。`Elfie` 只作为单精灵 facade 与生命周期边界，
认知算法由 Brain、神经处理由 NervousSystem、设备连接由 Body、数字消息由
Communication 分别拥有。

Body 输入必须先经过 NervousSystem；数字通信不经过 NervousSystem，而是与身体
感知并列写入 Brain 根层的 `PerceptualWorkspace`。BrainCoordinator 独立封口
frame、构建上下文和提交皮层任务；OutputRouter 是唯一输出入口。详细契约和时序
见 `docs/design/Elfie感知认知决策信息流.md`。

`elfie/state/`、`brain/cognition/` 和 `brain/brain_types.py` 已删除；禁止新增
`brain/perception/`。运行时情绪、能量和身体绑定由各模块内存维护，不聚合恢复。

## Desktop 与 Godot

```text
desktop/src/
├── main.ts
├── windows/
├── supervisor/
├── resources/
├── platform/
└── ipc/                # 有真实原生调用需求时再创建

godot/
├── project.godot
├── main.tscn
├── rooms/
├── characters/
├── scripts/
└── ui/
```

Desktop 只负责 Electron 宿主、窗口、平台差异、发布资源发现和子进程生命周期。Godot 是独立 4.7 源项目，负责房屋、坐标、导航、碰撞、相机和渲染。Godot Web 导出物不是源码，统一写入 `build/components/godot-web/`。

Desktop 目录的固定二级结构如下：

```text
desktop/
├── src/
│   ├── main.ts
│   ├── windows/
│   ├── supervisor/
│   ├── resources/
│   ├── platform/
│   └── ipc/
├── assets/
├── packaging/
├── package.json
├── pnpm-lock.yaml
└── tsconfig.json
```

`src/ipc/` 不是必建空目录；只有出现真实原生 IPC 调用时再创建。

## 构建产物和发布物

所有组件编译产物、staging 资源和最终安装包必须进入根目录下的统一位置：

```text
build/
├── components/
│   ├── godot-web/
│   ├── desktop/
│   ├── app-web/
│   └── python-core/
│       └── <platform-arch>/
├── staging/
│   └── <platform-arch>/
│       └── resources/
│           ├── godot-web/
│           ├── python-core/
│           └── ollama/
├── manifests/
└── stamps/

dist/
├── ElfieNest-<version>-arm64.dmg
├── ElfieNest-<version>-x64.exe
├── ElfieNest-<version>-x86_64.AppImage
└── checksums.txt
```

`build/staging/<platform-arch>/resources/` 是单平台 staging root。构建脚本不得在同一个
`resources/` 下面创建 `python-core/darwin/`、`python-core/win32/`、`ollama/linux/`
这类旧式多平台目录。Windows target 只在当前 target 的 `python-core/` 和 `ollama/`
目录内使用 `.exe` 文件名。

## 依赖方向

```text
app/interfaces
  -> app/features 或 app/orchestration
  -> elfie + nest + ai_runtime
  -> 所需端口
  -> app/infrastructure
```

`desktop` 启动 `app/bootstrap` 并监督运行组件；`nest/godot` 与已导出的 Godot Runtime 交换事件。`elfie`、`nest` 和 `ai_runtime` 不得反向导入 `app`；`elfie` 也不得导入 `nest` 或 `ai_runtime`。

## 测试和持续约束

测试目录镜像源码目录。`test/architecture/test_project_structure.py` 检查目标根目录、App/Nest/Desktop 二级结构、旧包消失和 Python 导入边界。任何目录调整必须先修改本规范，再同步更新 README、AGENTS.md 和结构契约测试。

## 延期范围

当前不创建 `connectivity/`。Nest-Nest 网络、中央信令服务、局域网发现、远程移动聊天 App 和房屋自由编辑需要后续专项设计；不得为了预留未来能力提前建立空的顶层实现。
