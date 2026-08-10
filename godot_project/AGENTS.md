# Godot 源工程执行规则

本目录是 Godot authority 的源工程，也是房屋、几何、坐标、移动、导航、碰撞和渲染
事实的唯一源码来源。

- Python 只能发送高层语义命令并接收已发生的物理事实，不得复制 Godot 的空间或
  物理权威。
- 协议帧、网络连接、进程宿主和 Python 侧 Adapter 属于系统 Infrastructure；本目录
  只实现 Godot 侧协议端点和 authority 行为。
- Actor 身体回执与全局世界事实是不同语义通道，但可以共享同一认证连接。
- Python 侧宿主、Gateway 和协议 Adapter 的目标归档由系统契约与 `SYS-001` 跟踪；
  `godot_project/` 永久保持独立，本规则不授权移动 Godot 工程或修改协议。
- 打开、运行、调试、截图或关闭 Godot 前，必须先读取并执行
  `../.agents/skills/godot-project-operator/SKILL.md`。
- 按该技能检查现有进程和 `project.godot` 声明的版本；未经用户同意不得用不匹配
  版本编辑项目，也不得创建重复实例。
- 操作前后检查 Git 状态，不保留 `.godot/`、导入缓存或编辑器自动产生的无关改动。
