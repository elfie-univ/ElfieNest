# ADR-0002：系统级嵌套 Ports/Adapters

- **状态：** 已接受
- **日期：** 2026-08-10
- **范围：** 全仓目标架构

## 背景

App 已采用轻量 Ports/Adapters，但具体持久化、模型、Godot、设备和文件能力仍散落在
根目录与领域目录。把所有当前目录视为同级模块会掩盖产品层级，也让技术细节进入
Elfie 和 Nest 测试。

## 决策

ElfieNest 采用嵌套式系统架构：

- `app/` 是上层产品/应用层；
- `elfie/` 和 `nest/` 是中间领域核心；
- 一套运行中的 ElfieNest 永远只有一个精灵巢；
- 目标根 `infrastructure/` 包含模型、工具、持久化、Godot、设备、通信和平台
  Adapter；
- 根 `godot_project/` 永久保持为独立 Godot 源工程和物理 authority，只有 Python
  宿主、Gateway 和协议接入进入 `infrastructure/godot/`；
- 当前 `ai_runtime/` 按职责拆解而不是整体移动：Provider/模型调用进入
  Infrastructure，Food 管理和报告进入 App Feature，Elfie 通过自有 Port 使用
  Food、模型和工具能力；
- 稳定的 Elfie/Nest Facade 直接承担入站 Port，除非有真实需求，否则不复制 Protocol；
- Elfie/Nest 拥有自己的语义出站 Port，Infrastructure 实现，Bootstrap 完成具体装配；
- Infrastructure 各能力包不得导入或构造彼此的具体 Adapter，由 Bootstrap 组合窄 Port；
- Orchestration 协调运行时工作流，但不是组合根；
- 普通 Food 读取、模型调用和工具执行直接使用注入 Elfie 的 Port，不经过 App
  Orchestration；
- actor-body 命令和 Nest 世界事实通过一个共享 Godot Gateway 的两条语义通道流动。

本决策确立宏观架构 v1。以后若改变模块所有权、authority、依赖方向、生产组合/
生命周期所有权或系统级 Port 语义，必须先建立新的独立 ADR 和版本化治理变更，再修改
实现。

## 后果

当前路径按精确一致性台账逐步迁移。领域测试可以使用 Fake，技术替换收敛在 Adapter，
Facade/Port 稳定时模块内部修改保持局部。代价是边界映射和 Bootstrap 装配更明确；有意
修改系统契约时仍然需要同时迁移相关模块。

当前不采用以下方案：为了一个配置套餐长期保留目标 `ai_runtime/` 模块、把它整体移动
到 Infrastructure、把 Godot 源工程移动到 Infrastructure、把 Godot 传输和进程代码
放进 Nest、让普通模型调用经过 Orchestration、允许领域 Core 构造技术依赖、全局万能
Repository、为每个 Facade 复制入站 Protocol，以及一次性移动全仓。
