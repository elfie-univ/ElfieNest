# 物种资源包契约

状态：规范性契约，版本 2

本契约定义一个物种什么时候才是 ElfieNest 可用的运行时物种。不能因为有
一个名字、一个档案、一张头像或一个占位场景，就把物种当成可选项。只有完整的
配置包和 Godot 资源包存在，并且都通过校验，物种才可以被选择。

## 配置包

唯一的注册文件是 `config/species/catalog.yaml`。每一条记录指向
`config/species/<package>/` 下的一个包，并声明稳定的技术 `species_id`、canon ID、
显示名称、状态（`draft`、`published`、`retired`）、排序和定义版本。物种包包含：

```text
<package>/
├── species.yaml       # canon、稳定 ID 和 Godot 包链接
├── appearance.yaml    # 可调控制项、范围和相关性
├── genesis.yaml       # 阶段范围、性格先验和偏好
└── assets/
    ├── headshot.png
    └── full-body.png
```

`published` 物种只有在全部类型化配置、Genesis 数据和两张不同的 PNG 资源都有效时
才能被领养。`retired` 物种仍可用于解析已有档案，但不再出现在领养选项中。`draft`
物种失败即关闭，不进入运行时选项。物种定义不包含候选名字；名字由领养过程中的
已配置模型生成。

只有 Infrastructure 可以读取 YAML 和路径。它校验物种包后，把不可变的类型化目录
注入 Profile、Genesis 和 Adoption。前端只从 API 获取图片 URL，不保存物种列表或图片
副本。PNG 只负责展示；3D 身体仍以 Godot 资源包为唯一事实源。

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
`schema_version: 2`，并包含：

- `species_id`、`scene_file`、`model_file`；
- 包含上述四个必需节点路径的 `required_nodes`；
- 包含 `movement`、`appearance`、`portrait`、`preview` 的
  `required_capabilities`；
- 包含全部必需动画名称的 `required_animations`；
- `shared_animation_files`，把每个必需动画名称映射到一个存在的
  `res://characters/animation/...` 资源；以及
- `package_version`、`appearance_protocol_version` 和每个语义外观控制项的
  类型化 `appearance_bindings`。

Manifest 把语义控制项绑定到具体骨骼或 blend shape。Python 只能发送语义外观值，不能
再维护一份 Godot 骨骼映射或渲染事实。

运行时会把 manifest 与已加载的场景、引用的模型、导入资源、节点树、网格、骨架
和动画源逐项比对。格式错误或不完整的资源包会被拒绝，并从 actor catalog 中
排除；前端不得用图片回退把它重新变成可选项。

## 注册和验收

新增物种必须同时提交配置包、匹配的 Godot 资源包，以及 Python 配置/目录和 Godot
catalog 两侧的测试。只有两个资源包都通过本契约，领域目录才能把物种标为
`published`。前端只读取 API 返回的 active species 列表和图片 URL，不维护第二份物种
列表，也不维护图片回退。

标准验证命令：

```sh
uv run --no-sync pytest -q \
  test/elfie/profile/test_species_registry.py \
  test/app/features/adoption/test_facade.py
godot --headless --path godot_project \
  --script scripts/test/test_species_catalog.gd
```
