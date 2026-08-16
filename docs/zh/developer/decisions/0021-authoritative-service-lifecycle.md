# ADR-0021：权威服务生命周期与独立能力健康

- **状态：** 已接受
- **日期：** 2026-08-15
- **范围：** 服务状态、入口、受管进程所有权与就绪判定

## 背景

ElfieNest 过去把 Core、Godot 和可选模型准备混成一个启动结果。Desktop 与源码 CLI
又通过不同的所有权和展示路径得到这个结果：次要组件变慢会把可用 Core 误判为失败，
PID 文件、端口或 UI 状态也可能冒充权威 Runtime 状态。

产品需要一个状态写入者、可独立使用的就绪层级，以及安装版 App、安装版 CLI 和源码
开发入口一致的生命周期语义。

## 决策

- 采用规范性的[服务生命周期契约](../contracts/service-lifecycle)及已审阅的[状态机设计](../designs/service-lifecycle-state-machine)。
- `app/orchestration/lifecycle` 是原子、按 generation 管理快照的唯一写入者。Backend
  只有 `OFFLINE`、`CORE_READY`、`WORLD_READY` 三个稳定层级，过渡阶段和失败独立表达。
- 模型健康是独立的持久证据投影。常用粮、保底粮和非活跃模型具有不同的聚合影响；启动
  不执行阻塞式推理验证。
- Godot 是精确 generation 的受管 Core 子进程。Ollama 只有预先存在的 `EXTERNAL` 或
  `ELFIENEST_OWNED` 两种所有权，并通过用户级 lease 共享。
- 打包 Desktop Controller 全局单实例且独立于可关闭的 Viewer。安装版 `elfienest start`
  激活同一个 Controller 和 Server，不打开 Viewer；源码 `./elfienest.sh` 仍是隔离开发入口。
- 身份、停止权限和恢复依据产品锁、规范化数据根、generation 与经过验证的进程身份，不能
  只依赖端口、PID 或进程名。安装版启动只使用已打包资源，绝不构建或安装产品依赖。

ADR-0014 继续作为即时启动展示与有界清理的历史证据。本决策取代其单一终态 `ready` 模型，
也取代“关闭 Viewer 就隐式停止 Server”的解释。

## 结果

Core 配置可以早于世界/模型收敛可用，部分失败可以如实表达，所有入口都连接到同一 authority。
实现需要快照 schema、命令串行化、进程 lease、能力门、安装器集成和阶段计时；当前缺口只记录
在[服务生命周期一致性台账](../conformance/service-lifecycle)中。
