# 物种资源包契约

状态：规范性契约，版本 1

本契约定义一个物种什么时候才是 ElfieNest 可用的运行时物种。不能因为有
一个名字、一个档案、一张头像或一个占位场景，就把物种当成可选项。只有完整的
Godot 资源包存在，并且通过运行时校验，物种才可以被选择。

## 资源包目录

每个运行时物种必须在 `godot_project/characters/` 下拥有自己的目录：

```text
<species_id>/
├── <species_id>.glb
├── <species_id>.tscn
└── species_manifest.json
```
资源包必须完整包含以下内容：

- 一个正式 `.glb`，里面必须有非空的可见网格和 `Skeleton3D`。
- 一个 `<species_id>.tscn`：根节点必须是 `CharacterBody3D`，其 `species_id`
  必须与目录名一致，并且必须引用正式 `.glb`。
- `VisualRoot`、`VisualRoot/character`、`AnimationPlayer` 和
  `CollisionShape3D` 四个节点。
- 可用的共享 `ElfieActor` 移动/外观运行时和主碰撞体。
- 由真实运行时外观链路实现的肖像和预览能力。静态 SVG 或其他回退图片不能
  代替真实能力。
- 全部公共动画资源和动画名称：`idle`、`walking`、`running`、`jump`、
  `twist_dance`、`left_strafe`、`left_strafe_walking`、`left_turn`、
  `left_turn_90`、`right_strafe`、`right_strafe_walking`、`right_turn`、
  `right_turn_90`。

## Manifest

`species_manifest.json` 是资源包的机器可读声明。必须使用
`schema_version: 1`，并包含：

- `species_id`、`scene_file`、`model_file`；
- 包含上述四个必需节点路径的 `required_nodes`；
- 包含 `movement`、`appearance`、`portrait`、`preview` 的
  `required_capabilities`；
- 包含全部必需动画名称的 `required_animations`；
- `shared_animation_files`，把每个必需动画名称映射到一个存在的
  `res://characters/animation/...` 资源。

运行时会把 manifest 与已加载的场景、引用的模型、导入资源、节点树、网格、骨架
和动画源逐项比对。格式错误或不完整的资源包会被拒绝，并从 actor catalog 中
排除；前端不得用图片回退把它重新变成可选项。

## 注册和验收

新增物种必须同时提交完整资源包、匹配的领域 canon/registry 条目，以及 Python
registry 和 Godot catalog 两侧的测试。领域 registry 只有在资源包通过本契约后，
才能把物种标为运行时支持。前端只读取 API 返回的 active species 列表，不维护
第二份物种列表，也不维护图片回退。

标准验证命令：

```sh
uv run --no-sync pytest -q \
  test/elfie/profile/test_species_registry.py \
  test/app/features/adoption/test_facade.py
godot --headless --path godot_project \
  --script scripts/test/test_species_catalog.gd
```
