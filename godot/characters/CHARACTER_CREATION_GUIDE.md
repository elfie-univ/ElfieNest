# ElfieNest 3D 动物角色创建与集成手册

本文描述从二维设定图到 Godot 可运行角色的完整生产流程。当前标准面向
拟人化双足动物，狗和狐狸是基准角色。四足形态只预留资源契约，暂不实现
运行时切换。

高矮胖瘦、脸型、五官、毛发、毛色、Shape Key 命名、随机生成范围和物种
配置见 [外貌参数与物种母版规范](APPEARANCE_SYSTEM_SPEC.md)。
已经完成骨架和蒙皮、准备实际制作语义区域与 Shape Key 时，使用
[Blender 动物外貌母版制作教程](BLENDER_APPEARANCE_AUTHORING_GUIDE.md)。

## 1. 最终交付标准

一个可接入项目的角色至少包含：

- 多视角一致的二维角色设定图。
- 一个无动画、T-Pose 或 A-Pose 的带蒙皮 GLB 模型。
- 与项目公共双足骨架契约兼容的主骨架。
- 3 至 5 节尾骨及连续、平滑的尾巴权重。
- 一个继承公共角色逻辑的 `CharacterBody3D` 包装场景。
- 可随身高和体型变化的主胶囊碰撞体。
- 材质、贴图、外观参数和装备插槽说明。
- Godot 导入、动画、碰撞和运行时验收记录。

角色源模型不应内嵌日常动作。待机、行走、跑步等动作统一保存在
`res://characters/animation/`，由公共控制器装载。

## 2. 目录与命名契约

```text
godot/characters/
├── animation/
│   ├── idle.fbx
│   ├── walking.fbx
│   └── ...
├── shared/
│   └── elfie_actor.gd
└── <species>/
    ├── <species>.glb
    ├── <species>.tscn
    ├── <species>_shaded.png
    └── source/             # 可选；Blender 源文件及许可证说明，必须包含 .gdignore
```

`source/` 是 DCC 制作源目录，不是 Godot 运行资源目录。目录中的 `.blend`、
制作预览和中间导出由 Blender 或仓库工具直接读取；`.gdignore` 阻止 Godot
扫描和自动导入这些文件。提交给 Godot 场景的稳定资产必须导出到物种目录的
`<species>.glb`，场景只引用该 GLB，不得直接引用 `.blend`。

物种标识使用小写 ASCII，例如 `dog`、`fox`。所有物种的运行时节点名称
保持一致：

```text
CharacterBody3D
├── VisualRoot
│   └── character
├── AnimationPlayer
└── CollisionShape3D
```

公共双足骨至少需要以下稳定名称：

```text
mixamorig:Hips
mixamorig:Spine
mixamorig:Spine1
mixamorig:Spine2
mixamorig:Neck
mixamorig:Head
mixamorig:LeftArm / RightArm
mixamorig:LeftForeArm / RightForeArm
mixamorig:LeftHand / RightHand
mixamorig:LeftUpLeg / RightUpLeg
mixamorig:LeftLeg / RightLeg
mixamorig:LeftFoot / RightFoot
mixamorig:LeftToeBase / RightToeBase
```

额外的手指、耳朵、下颌或辅助骨可以因物种而异，但不得修改公共骨名称。

## 3. 第一步：使用 Gemini 生成多视角设定图

工具入口：[Google Gemini](https://gemini.google.com/)。

先确定物种、拟人程度、比例、毛发、服装基线和材质风格，再生成至少四个
视角：正面、左侧、背面和四分之三视角。所有视角必须是同一个角色，不要
让眼睛颜色、耳朵长度、尾巴形状或服装在不同图片中变化。

建议提示词包含以下约束：

```text
同一只拟人化卡通狐狸的角色设定图，双足直立，全身完整可见。
同时展示正面、侧面、背面和四分之三视角。
保持面部、耳朵、尾巴、手脚比例和毛色完全一致。
中性 T-Pose，无服装遮挡身体轮廓，纯色背景，均匀工作室灯光。
```

生成后检查：

- 四肢、耳朵和尾巴没有被画面裁切。
- 正侧面身高、头身比和尾巴长度一致。
- 手指数量和脚掌结构在所有视角一致。
- 尾根位置清楚，不能被衣服或身体遮住。
- 眼睛、牙齿、毛发没有悬浮或重复结构。

原始设定图和最终采用版本应保存到角色源文件目录，并记录生成日期和使用
的模型名称。不要只保留压缩后的聊天截图。

## 4. 第二步：把图片转换为 3D 模型

当前流程曾使用 [Hyper3D Rodin](https://hyper3d.ai/) 完成 Image-to-3D。
免费额度和许可证可能变化，使用前必须重新确认下载、商用和再分发条件。

需要开源本地方案时可评估：

- [Tencent Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2)
- [Stability AI Stable Fast 3D](https://github.com/Stability-AI/stable-fast-3d)

“网页可以免费使用”和“模型代码开源”不是一回事。每个角色必须在源文件
目录记录实际使用的网站 URL、模型版本、许可证和生成日期。

生成设置建议：

- 选择完整角色、复杂几何和可用于游戏的预设。
- 优先使用无背景的正面图，并补充侧面或背面参考。
- 下载带 UV 和贴图的 FBX、OBJ 或 GLB。
- 保留未简化的源模型，同时导出一份游戏优化版本。

进入下一步前检查模型是否闭合，四肢是否分离清楚，尾巴是否与臀部正确
连接，以及眼球、牙齿等部件是否处于正确位置。

## 5. 第三步：使用 Mixamo 生成双足骨架和公共动作

工具入口：[Adobe Mixamo](https://www.mixamo.com/)。

### 5.1 自动绑定

上传不带骨架的角色，将定位点放到下巴、手腕、手肘、膝盖和腹股沟。
Mixamo 只理解人形结构，不会正确处理动物尾巴，也不会生成四足骨架。

绑定成功后下载两类文件：

1. 基础模型：T-Pose，`With Skin`，只用于角色模型和蒙皮。
2. 公共动作：`Without Skin`，优先勾选 `In Place`，只用于动画库。

不要用正在走路或跳舞的 FBX 作为后续尾巴手术的基础模型。

### 5.2 公共动作清单

至少准备 `idle` 和 `walking`，其余动作按需要加入：

```text
idle
walking
running
jump
left/right strafe
left/right turn
left/right turn 90
twist dance
```

公共动作必须只驱动公共双足骨。物种特有的尾巴、耳朵和面部动作不写入
公共 FBX，避免与 Godot 的程序化动画冲突。

## 6. 第四步：在 Blender 清理基础模型

工具入口：[Blender](https://www.blender.org/)。建议保存 `.blend` 源文件，
不要只保留最终 GLB。

Blender 与 Godot 的职责固定如下：Blender 负责建模、骨架、蒙皮、Shape Key、
材质制作和母版保存，并导出 GLB；Godot 负责导入 GLB、组装场景、动画控制、
碰撞和运行时渲染。不要让 Godot 直接导入 `.blend`，否则冷导入会隐式启动
本机 Blender，使构建结果依赖 Blender 版本和图形驱动状态。

### 6.1 先清除动画数据

如果基础 FBX 意外携带动作，必须在切割或改权重前彻底清除：

1. 选中 Armature，进入 Pose Mode，按 `A` 全选骨骼。
2. 使用 `Alt/Option + G`、`Alt/Option + R`、`Alt/Option + S` 清除姿态。
3. 在 Dope Sheet 的 Action Editor 中解除当前 Action。
4. 在 NLA Editor 中删除所有 NLA Strip。
5. 检查 Armature 的 Animation Data，确认没有残留 Action。
6. 时间轴拖到任意帧，模型都必须保持同一参考姿态。

只删除时间轴上可见的黄色关键帧并不充分，NLA 或仍链接的 Action 仍可能
在切开尾巴后让身体和尾巴错位。

### 6.2 修正 `HeadTop_End`

Mixamo 生成的 `mixamorig:HeadTop_End` 有时会远高于真实头顶：

1. 选中 Armature 并进入 Edit Mode。
2. 只选择 `HeadTop_End` 顶端控制点。
3. 按 `G` 将它移动到真实头顶附近。
4. 保持它是 `Head` 的子骨，不改变公共骨名称。

它通常不是变形骨，但规范的长度能避免调试、附件定位和自动工具误判角色
高度。

## 7. 尾巴清权重与生产级尾骨

### 7.1 首选方法：不切网格，直接清理权重

如果尾巴和身体拓扑正常，优先在 Weight Paint 或 Edit Mode 中选中尾巴
顶点，从腿、髋和脊柱的顶点组移除错误权重。这样不会破坏 UV、法线、材质
槽和尾根接缝。

### 7.2 权重无法修复时再分离尾巴

1. 备份 `.blend` 文件。
2. 在 Edit Mode 透视选择完整尾巴，确认没有选到臀部。
3. 按 `P`，选择 `Selection`，把尾巴临时分成独立对象。
4. 只删除尾巴对象上的错误骨骼权重，不删除 UV 和材质数据。
5. 清理完成后先选尾巴，再选身体，按 `Ctrl + J` 合并。
6. 只选择尾根接缝附近的顶点，以很小阈值执行 `Merge by Distance`。
7. 检查法线、UV 接缝和材质槽。

禁止全选整个高精度角色后用较大阈值合并，否则眼皮、嘴唇、手指和毛发层
等距离很近的顶点可能被误焊。

### 7.3 尾骨标准

单根 `mixamorig:Tail_Bone` 且整条尾巴权重为 `1.0`，只能实现刚性左右摆，
不能产生弹簧弯曲。正式角色应使用 3 至 5 节骨链：

```text
mixamorig:Hips
└── Tail_01
    └── Tail_02
        └── Tail_03
            └── Tail_04
```

要求：

- `Tail_01` 起点位于尾根旋转中心，而不是 `Hips` 原点。
- 骨链沿尾巴中心线排列，每节长度大致均匀。
- 尾根可少量混合 `Hips` 与 `Tail_01`，避免出现折痕。
- 中段顶点在相邻两节尾骨之间渐变。
- 尾尖主要由最后一节控制。
- 执行 `Weights > Normalize All`，单个顶点总权重为 `1.0`。
- 使用极端左右、上下弯曲姿态检查尾根是否撕裂或塌陷。

当前 dog 和 fox 仍只有一根 `mixamorig:Tail_Bone`，属于可导入但待升级的
过渡资源。增加尾骨链后，Godot 公共尾巴弹簧组件只需要读取骨名和物种参数。

## 8. 坐标、变换和导出 GLB

在没有 Action 和 NLA 的参考姿态下处理变换。需要应用旋转或缩放时，应同时
选择对应的 Armature 和蒙皮网格，并在副本中验证，避免单独应用导致 bind
pose 变化。

导出前检查：

- 网格和 Armature 的对象级旋转、缩放符合项目坐标约定。
- 模型脚底位于地面，整体朝向与 Godot 的 `-Z` 前方约定一致。
- 没有未使用相机、灯光、重复网格和隐藏测试物体。
- 基础模型不包含动作；尾巴、耳朵等物种骨保留。
- 材质使用可移植的 PBR 设置，贴图路径和许可证已记录。

导出 `glTF 2.0` 的 Binary `.glb`，启用 Skinning，选中需要的模型和骨架，
不要导出相机和灯光。导出后重新导入一个空 Blender 文件，确认模型、骨架、
蒙皮和贴图没有依赖原场景。

## 9. 第五步：Godot 场景、碰撞和防穿墙

Godot 版本必须与 `godot/project.godot` 的 `config/features` 一致。不要用更高
版本直接打开并提交自动升级后的项目文件。

### 9.1 为什么使用主胶囊

游戏角色的移动碰撞不是模型外皮。日常行走只使用一个稳定的凸形胶囊：

- `CharacterBody3D` 调用 `move_and_slide()` 与墙体 `StaticBody3D` 碰撞。
- 胶囊覆盖躯干和腿部的主要体积，但通常不覆盖展开的手臂和尾巴。
- 身高变化同步修改胶囊高度和中心位置。
- 胖瘦变化同步修改胶囊半径。
- 胶囊和视觉模型的底部都保持在角色原点 `Y=0`。

若给每条手臂、腿和尾巴都添加参与移动阻挡的碰撞体，挥手时角色会被墙
推开，经过门框时容易卡住，物理结果也会随动画帧抖动。因此不要用精细骨骼
碰撞替代主胶囊。

### 9.2 骨骼碰撞体何时使用

以下情况可以为头、躯干和四肢添加简化的胶囊或盒形命中体：

- 点击或触摸身体部位。
- 战斗或互动命中检测。
- 进入布娃娃状态后的物理模拟。

这些碰撞体必须放在独立碰撞层，正常移动时不与墙体发生阻挡。胳膊靠近
墙面时的视觉处理使用射线、距离限制和 Skeleton IK，而不是动态改变主碰撞
轮廓。

### 9.3 当前项目实现

`dog.tscn` 和 `fox.tscn` 都提供 `CharacterBody3D + CapsuleShape3D`。共享脚本
根据以下数据同步视觉和主胶囊：

```json
{
  "species": "fox",
  "height": "short",
  "build": "plump"
}
```

也支持连续数值 `height_scale` 和 `build_scale`，当前限制在 `0.85` 至 `1.15`。
碰撞体只能防止角色进入带碰撞的墙；新增房间墙体时仍必须提供
`StaticBody3D + CollisionShape3D`。

## 10. 公共动画与重定向

狗和狐狸的 Mixamo 主骨名称一致，可以共享双足动作，但骨长和参考姿态不同，
不能只凭文件能播放就认定验收通过。

每个新物种必须检查：

- `Hips`、脊柱、手臂和腿部层级与公共契约一致。
- Godot 导入后的动画轨道能找到对应的 `Skeleton3D` 骨骼。
- 待机、行走、跑步时脚底没有明显滑动。
- 肩膀、手腕和膝盖没有因参考姿态差异扭曲。
- 公共动画不控制 `Tail_01...Tail_04`、耳朵或面部骨。

比例差异较大时，使用 Godot humanoid bone map/retarget 流程，不为每个物种
复制整套公共动画。

## 11. 程序化尾巴弹簧

尾巴弹簧应在身体动画计算后叠加，推荐实现为共享 `SkeletonModifier3D`。
每节尾骨使用前一节的角度和角速度积分，参数由物种资源提供：

```text
骨列表：Tail_01, Tail_02, Tail_03, Tail_04
stiffness：回正强度
damping：阻尼
max_angle：最大摆角
motion_influence：移动加速度影响
mood_influence：情绪摆幅影响
```

不要让 AnimationPlayer 和尾巴脚本同时写同一条尾骨轨道。公共动作必须删除
尾巴轨道，或明确保证尾巴修改器最后执行。

## 12. 高矮胖瘦、颜色和装备

### 12.1 身高

小范围个体差异可以缩放 `VisualRoot.y`，并同步调整主胶囊高度。若需要腿长、
躯干长、头大等独立比例，应在 Blender 建立受限的骨骼比例方案并逐动作验收。

### 12.2 胖瘦

不要只对整个角色做横向缩放。正式方案是在 Blender 制作 `slim`、`plump`
等 Shape Key，导出为 glTF morph target，再由连续参数混合。衣服也必须提供
对应形变，否则会穿模。

### 12.3 颜色

使用区域遮罩区分主毛色、腹部、耳内、爪子等区域，并通过实例独有材质设置
颜色。禁止直接修改共享材质资源，否则一只精灵换色会影响所有实例。

### 12.4 衣服和配件

- 眼镜、帽子和项圈使用 `BoneAttachment3D` 挂到统一插槽。
- 背包等刚性配件挂到 `Spine2` 或专用 socket。
- 上衣和裤子是绑定同一 Skeleton 的独立蒙皮网格。
- 衣服需要体型 morph target，或提供 slim/standard/plump 版本。
- 被衣服完全覆盖的身体区域应隐藏或使用裁剪网格，降低穿模风险。
- 装备资源需要 `humanoid_common`、`dog_only`、`fox_only` 等兼容标签。

建议的个体外观数据：

```json
{
  "species": "fox",
  "height_scale": 0.96,
  "build_scale": 1.04,
  "morphs": {"plump": 0.35},
  "colors": {"fur": "#C85A32", "belly": "#F1D4B5"},
  "outfit_ids": ["hoodie_blue"],
  "accessory_ids": ["round_glasses"],
  "appearance_seed": 18427
}
```

## 13. 四足形态预留

参考图中的直立形态和自然四足形态不是同一套普通 Mixamo 动画的简单切换。
四足状态的脊柱、肩胛、髋部、腕踝受力和碰撞轮廓都不同。

未来建议按同一物种身份维护两套运动形态：

```text
dog_biped.glb        # 公共 humanoid 骨架和双足动画
dog_quadruped.glb    # 统一的 quadruped 骨架和四足动画
```

两者共享材质、颜色、装备身份和外观种子。运行时切换时替换运动形态场景，
同步世界位置、朝向、情绪和当前行为，并把主碰撞体从直立胶囊切换为水平胶囊
或多个简化凸体。没有完成四足骨架、动画和过渡动作前，不在当前角色脚本中
加入半成品切换分支。

## 14. 验收清单

### Blender

- [ ] 参考姿态没有 Action 或 NLA 残留。
- [ ] `HeadTop_End` 长度合理。
- [ ] 公共骨名称和层级没有改动。
- [ ] 尾巴使用 3 至 5 节骨链和渐变权重。
- [ ] 极端姿态下尾根不撕裂、不塌陷。
- [ ] GLB 重新导入 Blender 后仍完整。

### Godot

- [ ] 项目版本和编辑器版本一致。
- [ ] 角色场景根节点是 `CharacterBody3D`。
- [ ] 主胶囊底部位于地面并覆盖主要躯干。
- [ ] short/tall/slim/plump 时视觉与胶囊同步。
- [ ] 待机、行走和跑步动画能在所有物种上播放。
- [ ] 角色不能穿过带碰撞的墙和门框。
- [ ] 手臂动作不会把角色从墙边弹开。
- [ ] 没有缺失贴图、黑色材质或导入错误。

### 提交前

- [ ] 不存在指向已删除旧示例目录的资源引用。
- [ ] 运行 Python 资源路径测试。
- [ ] 在没有其他 Godot 实例时运行场景资源契约验证。
- [ ] 检查 `.import`、`project.godot` 和场景文件是否被编辑器意外升级。
- [ ] 记录模型、贴图、动画和生成工具的许可证。

## 15. 参考链接

- [Google Gemini](https://gemini.google.com/)
- [Hyper3D Rodin](https://hyper3d.ai/)
- [Tencent Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2)
- [Stability AI Stable Fast 3D](https://github.com/Stability-AI/stable-fast-3d)
- [Adobe Mixamo](https://www.mixamo.com/)
- [Blender 文档](https://docs.blender.org/)
- [Godot Skeleton3D 文档](https://docs.godotengine.org/en/stable/classes/class_skeleton3d.html)
- [Godot CharacterBody3D 文档](https://docs.godotengine.org/en/stable/classes/class_characterbody3d.html)

最后更新：2026-07-18
