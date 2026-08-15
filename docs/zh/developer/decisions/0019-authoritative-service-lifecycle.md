# ADR-0019：权威服务生命周期与独立能力健康

- **状态：** 已接受
- **日期：** 2026-08-15
- **范围：** 服务状态、入口、受管进程所有权与就绪判定

## 背景

ElfieNest 当前把 Core、Godot 和可选模型准备合成一个启动结果，Desktop 与源码 CLI
又通过不同的所有权和展示路径得到该结果。次要组件变慢时，已经可用的 Core 会被显示为
失败；PID 文件、端口或 UI 状态也可能被误当成权威 Runtime 状态。

产品需要唯一状态写入者、可独立使用的就绪层级，以及安装版 App、安装版 CLI 和源码
开发入口之间一致的生命周期语义。

## 决策

- 采用规范性的[服务生命周期契约](../contracts/service-lifecycle)及已审阅的
  [状态机设计](../designs/service-lifecycle-state-machine)。
- `app/orchestration/lifecycle` 是 generation 级原子快照的唯一写入者。Backend 稳定
  层级只有 `OFFLINE`、`CORE_READY`、`WORLD_READY`；过渡 phase 与失败单独表达。
- 模型健康是独立的持久化证据投影。常用粮、保底粮和非活跃模型对总览影响不同；启动
  不执行阻塞式真实推理验证。
- Godot 是准确 generation 的 Core 受管子进程。Ollama 只有启动前已存在的 `EXTERNAL`
  和 ElfieNest 启动的 `ELFIENEST_OWNED`，并通过用户级租约共享。
- 已打包 Desktop Controller 在每个 OS 用户下全局唯一，且独立于可随时关闭的 Viewer。
  安装版 `elfienest start` 激活该 Controller 和 Server但不打开 Viewer；源码
  `./elfienest.sh` 只作为隔离的开发入口。
- 身份、停止权和恢复依据产品锁、规范化数据根、generation 与已验证进程身份，不仅依赖
  端口、PID 或进程名。正式安装启动只使用打包资源，不安装依赖或现场构建产品。

ADR-0014 继续作为即时启动展示和有界收束的历史证据。本决策取代其中单一终点 `ready`
模型，以及“退出 Viewer 会隐式停止 Server”的任何解释。

## 后果

Core 配置界面可先于世界与模型收敛使用，部分故障能够真实降级，所有入口附着同一
authority。实现需要新的快照 Schema、命令串行化、进程租约、能力门禁、安装器集成和
阶段计时。当前差距只记录在临时的
[服务生命周期一致性台账](../conformance/service-lifecycle)中。
