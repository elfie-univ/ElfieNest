# Embodiment 编排规则

本目录协调真实 Elfie、Nest 与外部身体之间的产品工作流，不实现设备协议。

- 只使用 `elfie/`、`nest/` 的公开模型和本层拥有的 Port；不得导入持久化 Repository、
  LAN/Bluetooth Adapter、设备 SDK 或 Interface DTO。
- 负责 hosting、return-home、offline、body-switching 等跨 authority 状态机、回执、
  幂等与恢复；外部身体概念和行为契约仍属于 `elfie/body`。
- 设备身份、配对凭据和传输由根 `infrastructure/devices` 实现本层或 Feature 的 Port。
- 不通过 `db_path`、全局 Registry 或 Adapter Record 传递状态；Bootstrap 注入所有依赖。
- 每个命令必须验证 Elfie/身体绑定与当前 lease，不能信任调用方自报关系。
