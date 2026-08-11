# Observer 语义残留迁移边界规则

本目录只剩尚未从 Nest Session 私有依赖中解开的 Observer 语义投影，继承
`nest/AGENTS.md`。Python/Godot 协议、认证、Session 和 Bundle 已迁至
`infrastructure/godot/gateway/`；不得把这些技术实现或兼容 Alias 放回本目录。

- 只接收高层语义命令和已发生物理事实；禁止在 Python 复制几何、导航、碰撞、坐标
  或渲染权威。
- 共享连接上的 actor body 回执与 Nest world 事实使用不同强类型通道；全局世界事实
  必须进入 Nest 规则，不能直接广播给 Elfie 绕过 Nest。
- 不新增业务规则、产品授权、数据库事实、进程生命周期所有权或新的原始 JSON 公共
  API。协议必须版本化、认证、限权，并具有超时、取消和终态回执。
- 当前目录只允许维护安全和收缩。等 APP-G06 用消费方 Port Model 解开
  `ObserverSemanticEntity` 后删除本文件和旧目录，不保留 import Alias 或双入口。
