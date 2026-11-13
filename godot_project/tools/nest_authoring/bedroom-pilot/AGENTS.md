# 卧室家具试点编辑规则

这里保留 V044 的 M01 卧室组件试点，供 Blender 编辑与 Godot 单独验证。正式卧室
使用 `res://nest/furniture/layouts/bedroom/bedroom-layout.scn` 和它引用的家具套装。

- `bed/` 的一份模型包含床壳、褥垫、被子、枕头、搭毯、缝边和固定灯带。
  不将这些部件继续拆成文件，内部命名节点须保留，以支持独立床品动作。
- `chair/` 包含整把转椅和坐垫。四个位置共享模型，材质与可变状态属于各自实例。
- `desks/a/`～`desks/d/` 是四种贴墙书桌，禁止因名字或柜体相似合并桌面。
- 每个 `source/*.blend` 是从确认后的 V044 最终几何重建的创作源，非遗失的历史原稿。
  后续形状编辑入口仍是对应 blend。GLB 只作编辑交换候选，不宣称其往返保留原生网格编码。
- 试点的原生 `.scn` 直接保留确认版网格缓冲；同目录的 `bedroom.tscn` 引用六个组件。
  `.scn` 是生成资源，禁止分别手改其几何制造第二编辑来源。未来从 blend/GLB 重新生成时，
  必须重新核对编码和画面，不能套用这次的原生保真证据。保留模块、住户、部件、
  接触点语义；几何共享不代表运行时状态共享。动态变形必须持有实例私有的可变 mesh。
- `source/.gdignore` 阻止 Godot 自动导入创作源。Blender 内查看附近建筑时仅作只读参照，
  不把建筑导出进家具。运行时不引用 source 或 build 目录。
- 试点上层目录须允许 Godot 导入 GLB，便于新工作区打开场景和运行验证。
- 试点引用的共用贴图由 `res://nest/furniture/textures/` 持有。试点场景和模型随
  `tools/` 排除在正式发行包外。
- 从仓库根验证试点场景：

  ```bash
  bash scripts/quality/checks/godot_host.sh res://test/test_bedroom_component_sharing.gd
  ```
