# Elfie Skills 迁移边界规则

本目录是 `ELF-002` 登记的临时旧位置；Skills 的目标所有者是
`elfie/brain/skills/`。

- 这里只允许为获批迁移切片维护现有行为；不得新增永久能力、Runtime 代理、平台工具、
  工作区路径或具体工具执行。
- Skill 只声明语义 `tool_key`/能力、参数约束、策略和授权结果；实际执行由 Brain 注入的
  `ToolPort` 完成，Adapter 仍保留全局可用性和逐次技术安全否决权。
- 随源码发布的不可变声明和内存策略不建立 Store；可变 Skill 安装或持久状态在单独契约
  获批前保持禁用，Skill 代码不得通过路径先制造事实源。
- 迁移必须一次更新全部生产调用方和测试，然后删除本目录；禁止保留 import alias、双包
  同步或 fallback。
