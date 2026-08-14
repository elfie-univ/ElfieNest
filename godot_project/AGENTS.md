# Godot 源工程执行规则

本目录是 Godot authority 的源工程，也是房屋、几何、坐标、移动、导航、碰撞和渲染
事实的唯一源码来源；与 Nest 的语义分工同时受
[`Nest–Godot semantic-world contract`](../docs/developer/contracts/nest-godot-semantic-world.md)
约束。目录按能力组织，不得预建空结构或在结构调整中夹带未验证的行为改动。

- Python 只能发送高层语义命令并接收已发生的物理事实，不得复制 Godot 的空间或
  物理权威。
- 协议帧、网络连接、进程宿主和 Python 侧 Adapter 属于系统 Infrastructure；本目录
  只实现 Godot 侧协议端点和 authority 行为。
- Actor 身体回执/感知、Nest 语义世界事实与 Runtime 控制事件是不同语义线路，但可以
  共享同一认证连接。每条事件必须携带明确类型和目标；Godot 不默认广播给所有 Actor。
- Godot 负责可见实体、声音可达、路径、碰撞和实际对象状态的物理判断；不保存 Home、
  居民归属、家庭规则或说话内容。MVP 结构化视觉不要求每只 Elfie 建渲染 Viewport，
  虚拟听觉也不以 TTS→STT 作为听见判据。
- `rooms/`、`characters/` 是物理场景与运行内容，不因不对应 Nest 业务模块而删除；
  `runtime/actor` 只负责身体执行，空间可见性和可听性归 `runtime/world`。Observer、Lab
  与 UI 是展示/开发模式，不取得 authority。
- `scripts/test/`、`scripts/tools/`、角色创作工具和 Source 树属于开发/创作输入，必须从
  每种发布导出中排除。无引用 Helper、参考场景或生成边车只能在 Scene、Preload、CLI、
  文档和导出引用都已排除后逐项删除，不得把目录清理变成资产批量删除。
- Python 侧宿主、Gateway 和协议 Adapter 只属于根 `infrastructure/godot/`；
  `godot_project/` 永久保持独立，本规则不授权移动 Godot 工程或修改协议。
- 打开、运行、调试、截图或关闭 Godot 前，必须先读取并执行
  `../.agents/skills/godot-project-operator/SKILL.md`。
- 按该技能检查现有进程和 `project.godot` 声明的版本；未经用户同意不得用不匹配
  版本编辑项目，也不得创建重复实例。
- 操作前后检查 Git 状态，不保留 `.godot/`、导入缓存或编辑器自动产生的无关改动。
