# 当前架构

这份文档描述 ElfieNest 当前代码中的模块边界与运行链路。它不是历史路线图，也
不会把尚未实现的设计写进当前架构。

## 系统地图

```text
Electron Desktop
        │ 监督进程、窗口与平台资源
        ▼
Python Core: app
   ├── orchestration ──> elfie
   │                ├──> nest
   │                └──> ai_runtime
   ├── features
   ├── interfaces
   └── infrastructure
        │
        └──────────────> Godot Web Runtime
```

核心源码按职责分为：

| 模块 | 当前职责 | 详细入口 |
| --- | --- | --- |
| `elfie/` | 一只完整精灵的档案、大脑、神经系统、身体、通信与技能 | [Elfie README](https://github.com/elfie-univ/ElfieNest/blob/main/elfie/README.md) |
| `nest/` | 活动空间状态、环境时钟、互动和 Godot 协议边界 | [Nest README](https://github.com/elfie-univ/ElfieNest/blob/main/nest/README.md) |
| `ai_runtime/` | 模型、Provider、策略、粮食、工具与安全运行时 | [AI Runtime README](https://github.com/elfie-univ/ElfieNest/blob/main/ai_runtime/README.md) |
| `app/` | 产品用例、接口、基础设施和跨模块编排 | [App README](https://github.com/elfie-univ/ElfieNest/blob/main/app/README.md) |
| `desktop/` | Electron 生命周期、资源发现和进程监督 | [Desktop README](https://github.com/elfie-univ/ElfieNest/blob/main/desktop/README.md) |
| `godot_project/` | 独立 Godot 源工程：房间、几何、坐标、碰撞、角色和渲染源码 | [Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot_project/README.md) |
| `devtools/` | 与普通用户产品隔离的模块实验台 | [Devtools README](https://github.com/elfie-univ/ElfieNest/blob/main/devtools/README.md) |

## 模块边界

`app/orchestration/NestSession` 是真实 `Elfie` 实例与 `Nest` 的唯一组合位置。
它按 ID 把巢内事件交给对应精灵，也负责把认知 Runtime 注入精灵生命周期。

`Nest` 自己只维护居民 ID、巢内语义状态、环境时钟与互动传播。它不创建或保存
真实 Elfie 对象，也不复制 3D 空间事实。

房屋、几何、世界坐标、移动、碰撞体、导航和渲染的唯一源码来源是独立 Godot 源工程 `godot_project/`。
Python 侧只保存产品规则所需的语义状态，并通过明确协议与导出的 Godot Runtime
交换事件。

依赖方向由 `test/architecture/` 持续检查。底层领域模块不能为了调用产品功能
而反向依赖 `app.interfaces`。

## 精灵、Nest 与 Godot Runtime 的交互

`godot_project/` 是开发时编辑的 Godot 源工程，并不是 Python 在运行时导入的
目录。构建会把它导出为 Godot Runtime；Python 侧通过 `nest/godot/` 的协议边界
与这个已运行的 Runtime 交换语义命令和世界事实。

```mermaid
flowchart LR
    Source["godot_project/<br/>Godot 源工程"]
    Runtime["Godot Runtime<br/>导出的 Web 或桌面运行时"]
    Elfie["elfie/<br/>认知、身体输出与通信输出"]
    Orchestration["app/orchestration/<br/>真实 Elfie 与 Nest 的组合、路由"]
    Nest["nest/<br/>房间语义、居民状态与世界事件"]
    Adapter["nest/godot/<br/>Godot Runtime 协议适配"]

    Source -->|"导出构建"| Runtime
    Elfie -->|"抽象行动与通信输出"| Orchestration
    Orchestration -->|"成员、住处与房间规则"| Nest
    Orchestration -->|"世界配置、角色目录与身体语义命令"| Adapter
    Adapter -->|"Runtime 协议"| Runtime
    Runtime -->|"运行时事件与物理事实"| Adapter
    Adapter -->|"校验后的世界目录、镜像与物理事件"| Orchestration
    Orchestration -->|"应用语义状态与互动传播"| Nest
    Orchestration -->|"身体感知、通信感知或执行回执"| Elfie
```

构建阶段先把 `godot_project/` 导出为可运行的 Godot Runtime。连接使用仅支持
v2 的 nonce 鉴权和单权威 generation；编排层先配置世界，等待 Runtime 发布语义
目录并声明导航就绪，再发送完整角色目录。运行期间，精灵输出抽象行动或通信内容；
`app/orchestration/` 按精灵 ID 经 `nest/godot/` 发送语义命令，Nest 自身不复制
坐标和家具事实。Runtime 运行空间、导航、动作、碰撞和渲染，并将发生的物理事实
回传。同一条回程经由编排层更新 Nest 语义状态，并成为对应精灵的身体感知、通信
感知或动作执行回执。

移动采用“目标级命令、引擎逐帧执行”的粒度。大脑发出一次
`execute_intent(intent="move_to_anchor")`，Godot 负责路径、步进、碰撞和动画；Python 只接收接受、开始、
完成、阻塞、取消、超时和触觉等决策相关事实。这样既充分使用 Godot 物理世界，
又不会让模型参与每一帧控制。

## 类型化认知信息流

Elfie 的物理感知与数字通信是两条独立输入通道：

```text
Body -> NervousSystem --------\
                               -> PerceptualWorkspace
Communication ----------------/          │
                                          ▼
                                  BrainCoordinator
                                          │
                              BrainContext + 模型回合
                                          │
                                          ▼
                                    DecisionPlan
                                          │
                                          ▼
                                     OutputRouter
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                        身体             通信           内部执行器
                          └──────── ExecutionReceipt ─────┘
                                          │
                                          └──> PerceptualWorkspace
```

`ElfieNestEngine.tick_once()` 推进 Nest 和精灵自身时钟，再泵送身体事件；它不会
等待模型推理或输出执行完成。每只精灵的 `BrainCoordinator` 独立封装感知帧，
`OutputRouter` 原子接收完整 `DecisionPlan`，执行结果再作为回执回到工作区。

这些内部契约由 Pydantic 类型定义。需要 JSON Schema 的调用方可以在运行时对
公开模型调用 `model_json_schema()`；仓库不维护第二份磁盘 Schema。

## 进程边界

开发态和安装态的组件不都运行在一个进程里：

```text
Electron Desktop
  ├── 普通用户窗口
  ├── Ollama（受管或外部）
  ├── Python Core
  └── 隐藏 Godot Web Runtime
```

Desktop 只负责单实例窗口、平台资源发现、进程监督和退出收束。账户、领养、
聊天、Nest 规则与 Elfie 认知仍属于 Python Core。Godot Web Runtime 在隐藏的
Chromium 窗口中持续运行，负责空间世界；模型服务可以是本地 Ollama 或由 Runtime
配置的其他 Provider。

## 数据与产物边界

三类路径不能混用：

| 内容 | 唯一位置 |
| --- | --- |
| 生产配置、数据库、精灵数据和本地密钥 | `${ELFIE_HOME:-~/.elfienest}` |
| 可再生的中间构建产物 | 根目录 `build/` |
| 最终发行安装包 | 根目录 `dist/` |

测试和实验必须使用隔离的 `ELFIE_HOME`。生成的 Godot Web、Desktop JavaScript
和 Python Core 不能写回源码目录；`build/` 与 `dist/` 都不提交 Git。

## 实现范围与扩展方式

架构页只描述代码、测试和稳定配置已经共同确认的边界。桌面安装包、平台适配和
更高层产品能力需要分别经过实现、测试和负责人审阅，不能从架构图自动推导出来。

当一项新的系统能力形成独立主题，并且有可定位的代码与测试证据时，再以单独的
Developer 文章加入对应侧栏；讨论稿和中间设计留在私有知识区。
