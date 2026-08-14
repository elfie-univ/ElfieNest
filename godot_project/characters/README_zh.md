# 角色资源

> 中文版：本文件 · [English](README.md)

`godot_project/characters/` 保存可复用的物种模型、公共动画和角色运行时脚本。
房间、家具、摄像头与角色资源保持分离。

角色资源只负责物种外观和具身表现，不是完整精灵身份。精灵的物种、外貌、
人格、能力、记忆和运行状态属于 `elfie/`；当前职责边界见
[Elfie 模块说明](../../elfie/README_zh.md)和
[Developer 架构文档](../../docs/zh/developer/architecture/index.md)。

## 当前结构

```text
characters/
├── animation/              # Mixamo 公共双足动画库
├── shared/
│   └── elfie_actor.gd      # 移动、动画装载和自适应主碰撞体
├── dog/
│   ├── dog.glb
│   └── dog.tscn
├── fox/
│   ├── fox.glb
│   └── fox.tscn
├── cat/
│   └── cat.tscn              # Myelle 程序化视觉资源 v0.1
├── CHARACTER_CREATION_GUIDE.md
├── BLENDER_APPEARANCE_AUTHORING_GUIDE.md
└── APPEARANCE_SYSTEM_SPEC.md
```

当前可选择物种是 Saevi（灵狐）、Tovren（灵犬）和 Myelle（灵猫）。Myelle
首版运行时视觉使用可复用的代码原生场景，后续可以替换为正式猫模型；它仍然
遵守相同的角色、碰撞、外观和动画名称契约。运行时按照 `species` 选择场景；
旧数据没有 `species` 时，保留现有的稳定回退规则。

## 运行时碰撞原则

- `CharacterBody3D` 的主胶囊负责地面移动、墙体和门框阻挡。
- 主胶囊随 `height`、`build` 或数值化外观参数同步变化。
- 胳膊、腿和尾巴不参与日常移动阻挡，避免动画动作把角色卡在墙上。
- 骨骼命中盒只用于触摸、命中检测或布娃娃，必须使用独立碰撞层。
- 手脚视觉贴墙属于 IK 和动作约束，不使用复杂移动碰撞体解决。

## 资源边界

- 物种共享资源只保存一份，不为每个精灵复制 GLB、动画或贴图。
- 个体差异由 `elfie_id` 对应的外观数据描述，不写回共享资源。
- 新物种必须提供自己的薄包装场景，并复用 `shared/elfie_actor.gd`。
- 公共双足动画必须通过统一骨架映射验证后才能加入 `animation/`。
- 四足形态未来作为独立运动形态资源接入，当前不在运行时启用。

完整生产流程与验收清单见
[角色创建与集成手册](CHARACTER_CREATION_GUIDE.md)。外貌参数、Blender
Shape Key、物种配置和随机生成约束见
[外貌参数与物种母版规范](APPEARANCE_SYSTEM_SPEC.md)。实际制作区域、骨骼
比例、Shape Key 和毛色遮罩时，按
[Blender 动物外貌母版制作教程](BLENDER_APPEARANCE_AUTHORING_GUIDE.md)
逐步操作。
