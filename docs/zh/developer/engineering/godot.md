# Godot

Godot 是房屋、几何、世界坐标、移动、碰撞、角色和渲染的唯一源码来源。

## 允许放在 Godot 的内容

- 场景、节点、房间和家具资源；
- 角色模型、动画、碰撞和导航；
- Web Runtime 的渲染与空间交互；
- 与 Python Core 交换事件的适配层。

## 不应放在 Godot 的内容

- Elfie 的完整身份、记忆和人格；
- Nest 的产品账户、领养和聊天规则；
- Python 侧复制的房屋蓝图或坐标事实。

打开、运行或截图前，先核对 `project.godot` 的 Godot 版本和已有进程，再按
[Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot_project/README.md)
与 `godot_project/WEB_EXPORT.md` 的流程操作。

## 居民状态接线

权威 Gateway 使用协议 4。环境命令单独携带 `life_phase`，不受灯光覆盖影响：
白天／黎明所有门常开，黄昏／夜间使用已有感应与防夹控制。所有精灵均可进入所有房间。

正式 Nest 会话选择 Brain 具身输入。寄身前必须取得精灵已在自己的床上躺好的权威状态；
选中实体身体后，虚拟身体留床并显示罩体。已提交的领养标识与时间驱动四楼单向到达展示，
重连不会重置到达时钟。没有传送离开，也不加入声音展示。

聚焦场景验证：`bash scripts/quality/checks/godot_host.sh
res://scripts/test/test_resident_lifecycle.gd`。真实设备寄身及最终画面验收仍需单独完成。
