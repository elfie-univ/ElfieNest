# Godot Gateway 迁移边界规则

本目录是当前 Python/Godot 协议接入实现，继承 `nest/AGENTS.md`。它属于已登记迁移
路径，不是 Nest 的长期技术所有权。

- 只接收高层语义命令和已发生物理事实；禁止在 Python 复制几何、导航、碰撞、坐标
  或渲染权威。
- 共享连接上的 actor body 回执与 Nest world 事实使用不同强类型通道；全局世界事实
  必须进入 Nest 规则，不能直接广播给 Elfie 绕过 Nest。
- 不新增业务规则、产品授权、数据库事实、进程生命周期所有权或新的原始 JSON 公共
  API。协议必须版本化、认证、限权，并具有超时、取消和终态回执。
- 目标位置是 `infrastructure/godot/`。当前目录只允许维护安全和收缩；迁移完成后删除
  本文件和旧目录，不保留 import Alias 或双协议入口。
