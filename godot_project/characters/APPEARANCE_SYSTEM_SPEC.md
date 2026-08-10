# ElfieNest 外貌参数与物种母版规范

本文定义精灵个体可以配置的外貌参数、参数之间的统计关系、每个物种母版
需要制作的骨骼、Shape Key、材质遮罩，以及从随机基因到 Godot 运行时形象
的完整数据流程。

外貌只是完整个体档案的一部分。物种、运动形态、人格、背景、偏好、能力、
记忆和运行状态由 `elfie/` 负责；当前模块与系统边界见
[Elfie 模块说明](../../elfie/README.md)和
[Developer 架构文档](../../docs/developer/architecture/index.md)。

本文是外貌系统的设计契约，不替代角色从图片到 GLB 的制作流程。基础模型、
骨架和尾巴制作见 [角色创建与集成手册](CHARACTER_CREATION_GUIDE.md)。在
Blender 中建立语义区域、骨骼比例、Shape Key、毛色遮罩和极值验收时，按
[Blender 动物外貌母版制作教程](BLENDER_APPEARANCE_AUTHORING_GUIDE.md)
操作。

## 1. 目标与边界

外貌系统需要满足：

- 同一物种只制作一套可变形母版，不为每只精灵重新雕刻模型。
- 个体外貌由稳定参数和随机种子决定，重新加载后不能改变。
- 大多数随机个体比例协调，极端或局部特殊体型只占少数。
- 正面头像中也能区分不同精灵，不能只依靠身高或衣服。
- 公共动画的骨骼名称和层级保持稳定。
- 狗、狐狸、猫、兔等物种共享参数语义，但分别配置范围和模型映射。

当前不要求：

- 用一份几何网格覆盖所有物种。
- 在运行时生成或修改 GLB 文件。
- 让任意未经准备的 AI 生成模型自动支持全部参数。
- 在第一版中实现完整毛发粒子、布料模拟或四足形态切换。

## 2. 核心概念

### 2.1 公共参数契约

公共契约只描述语义，例如“腿躯干比”“脸颊丰满度”“耳朵大小”。它不包含
Blender 顶点、骨骼索引或材质节点名称。

### 2.2 物种母版

每个物种拥有独立的 GLB 和 `SpeciesAppearanceProfile`。物种配置负责把公共
语义映射到本物种的骨骼、Shape Key、Shader 参数和允许范围。

### 2.3 个体外貌基因

每只精灵只保存 `AppearanceGenome`。连续随机变量使用以下约定：

- 宏观潜变量使用 `[-2.0, 2.0]` 的截断正态值，`0` 表示物种平均值。
- 局部偏差使用 `[-1.0, 1.0]`，允许正负变化，`0` 表示没有局部偏差。
- 枚举使用稳定字符串 ID。
- 颜色使用物种色板 ID 加有限的色相、饱和度和明度偏移。

### 2.4 解析后外貌

`ResolvedAppearance` 是经过物种范围、相关性和约束计算后的最终数据，包含
实际比例、骨骼缩放、Shape Key 权重和材质参数。Godot 只应用解析后的结果，
不自行重新随机。

## 3. 参数分层与应用顺序

外貌按固定顺序解析，避免不同参数争夺同一个含义：

```text
物种中性母版
  -> 整体身高
  -> 头、颈、躯干、手臂、腿的骨架比例
  -> 骨架粗壮度、脂肪和肌肉宏观体型
  -> 胸、腰、腹、臀、四肢等局部轮廓
  -> 头部内部的脸型和五官
  -> 毛发轮廓、毛色和花纹
  -> 不对称标记和附件
  -> 表情与身体动画
```

`head_torso_ratio` 控制整个头相对躯干的大小；脸部参数只在头部局部坐标中
改变轮廓和五官。最终脸宽按以下层级计算：

```text
最终脸宽 = 物种基础脸宽 × 头部整体缩放 × 局部脸宽缩放
```

因此头身比和脸宽不是重复参数。

## 4. 身体参数

### 4.1 整体与骨架比例

以物种中性母版的躯干长度为内部基准 `1.0`。个体基因保存相对物种平均值的
偏差，物种配置负责映射到实际比例。

| 字段 | 范围 | 含义 | 实现 |
|---|---:|---|---|
| `stature_z` | `[-2, 2]` | 整体身高潜变量 | `VisualRoot` 或全骨架统一缩放 |
| `head_torso_bias` | `[-1, 1]` | 头部高度/躯干长度 | 头部比例骨骼 |
| `neck_torso_bias` | `[-1, 1]` | 脖子长度/躯干长度 | 颈部比例骨骼 |
| `arm_torso_bias` | `[-1, 1]` | 手臂长度/躯干长度 | 上臂、前臂比例骨骼 |
| `leg_torso_bias` | `[-1, 1]` | 腿长/躯干长度 | 大腿、小腿比例骨骼 |
| `shoulder_torso_bias` | `[-1, 1]` | 肩宽/躯干长度 | 肩部比例骨骼和修正 Shape Key |
| `hand_arm_bias` | `[-1, 1]` | 手掌相对手臂大小 | 手骨缩放和手掌 Shape Key |
| `paw_leg_bias` | `[-1, 1]` | 脚掌相对腿部大小 | 脚骨缩放和脚掌 Shape Key |

物种配置必须给出实际最小值、基础值和最大值。例如：

```json
{
  "head_torso_ratio": {"min": 0.42, "base": 0.48, "max": 0.55},
  "neck_torso_ratio": {"min": 0.10, "base": 0.14, "max": 0.18},
  "arm_torso_ratio": {"min": 0.82, "base": 0.89, "max": 0.96},
  "leg_torso_ratio": {"min": 0.88, "base": 0.98, "max": 1.08}
}
```

比例映射使用平滑插值，不允许越过物种范围。整体高度在比例计算完成后统一
应用，避免头、躯干和腿分别随机后无法满足最终身高。

### 4.2 宏观体型潜变量

| 字段 | 范围 | 含义 |
|---|---:|---|
| `frame_size_z` | `[-2, 2]` | 骨架和关节的粗壮程度 |
| `body_fat_z` | `[-2, 2]` | 全身软组织和脂肪程度 |
| `muscularity_z` | `[-2, 2]` | 肩胸和四肢肌肉程度 |

这三个变量不得合并：大骨架、肥胖和肌肉发达是不同体型。

### 4.3 局部身体偏差

局部偏差不是最终尺寸，而是“相对同等宏观体型的平均个体更大还是更小”。

| 字段 | 范围 | 影响区域 |
|---|---:|---|
| `chest_fullness_bias` | `[-1, 1]` | 胸部宽度和厚度 |
| `waist_width_bias` | `[-1, 1]` | 腰部横向宽度 |
| `belly_depth_bias` | `[-1, 1]` | 腹部向前凸出程度 |
| `hip_width_bias` | `[-1, 1]` | 臀部横向宽度 |
| `hip_depth_bias` | `[-1, 1]` | 臀部前后厚度 |
| `arm_thickness_bias` | `[-1, 1]` | 胳膊粗细 |
| `leg_thickness_bias` | `[-1, 1]` | 腿部粗细 |
| `neck_thickness_bias` | `[-1, 1]` | 脖子粗细 |
| `paw_fullness_bias` | `[-1, 1]` | 手掌和脚掌肉感 |

“三围”不直接保存一个圆周数值。胸、腰、臀在 3D 中需要区分横向宽度和
前后厚度，最终围度由解析后的网格尺寸派生。

## 5. 宏观体型与局部轮廓的相关性

所有脂肪相关部位共享 `body_fat_z`，局部偏差只占较小权重：

```text
arm_softness_z   = 0.75 * body_fat_z + 0.25 * arm_thickness_bias
leg_softness_z   = 0.80 * body_fat_z + 0.20 * leg_thickness_bias
belly_softness_z = 0.90 * body_fat_z + 0.25 * belly_depth_bias
face_softness_z  = 0.65 * body_fat_z + 0.30 * cheek_fullness_bias
neck_softness_z  = 0.70 * body_fat_z + 0.20 * neck_thickness_bias
```

系数属于物种配置，不硬编码在公共生成器中。狗、狐狸、猫可以使用不同的
脂肪分布灵敏度。

骨架和肌肉同样参与部分轮廓：

```text
arm_final_z = arm_softness_z
            + frame_arm_weight * frame_size_z
            + muscle_arm_weight * muscularity_z

leg_final_z = leg_softness_z
            + frame_leg_weight * frame_size_z
            + muscle_leg_weight * muscularity_z
```

实际缩放使用对数尺度，避免负尺寸：

```text
part_scale = base_scale * exp(sensitivity * final_z)
```

宏观潜变量和局部偏差都是正态变量时，线性阶段仍保持正态分布，并且所有
部位通过共享潜变量自然相关。指数映射后尺寸呈以物种基础值为中心的有限
对数正态分布，更适合正尺寸数据。

必须增加一致性约束：

- `body_fat_z > 1.2` 时，胳膊、腿、腹部、颈部和脸部软组织结果不得为负。
- `body_fat_z < -1.2` 时，大多数软组织结果不得为正。
- 局部偏差不能完全抵消极端宏观体型。
- 不满足约束的候选参数重新采样，不依赖最终粗暴裁剪。

## 6. 脸部参数

脸部分为结构、五官和软组织。取消含义重叠的整体 `face_height`，改用明确的
局部组成。

### 6.1 脸部结构

| 字段 | 范围 | 含义 | 推荐实现 |
|---|---:|---|---|
| `skull_width_bias` | `[-1, 1]` | 头骨横向宽度 | Shape Key |
| `forehead_height_bias` | `[-1, 1]` | 额头高度 | Shape Key |
| `forehead_width_bias` | `[-1, 1]` | 额头宽度 | Shape Key |
| `jaw_width_bias` | `[-1, 1]` | 下颌宽度 | Shape Key |
| `cheekbone_width_bias` | `[-1, 1]` | 颧部结构宽度 | Shape Key |
| `cheek_fullness_bias` | `[-1, 1]` | 脸颊肉感局部偏差 | Shape Key |
| `lower_face_fullness_bias` | `[-1, 1]` | 下半脸肉感 | Shape Key |
| `muzzle_length_bias` | `[-1, 1]` | 口鼻向前长度 | Shape Key/面部骨 |
| `muzzle_width_bias` | `[-1, 1]` | 口鼻横向宽度 | Shape Key |
| `muzzle_height_bias` | `[-1, 1]` | 口鼻垂直厚度 | Shape Key |

最终脸部肉感由宏观胖度与脸部局部偏差共同决定：

```text
cheek_final_z = species_face_fat_weight * body_fat_z
              + species_face_frame_weight * frame_size_z
              + species_face_bias_weight * cheek_fullness_bias
```

### 6.2 眼睛和眼皮

| 字段 | 范围 | 含义 | 推荐实现 |
|---|---:|---|---|
| `eye_size_bias` | `[-1, 1]` | 眼球和眼眶大小 | 眼球骨缩放、眼眶 Shape Key |
| `eye_spacing_bias` | `[-1, 1]` | 两眼间距 | 左右眼骨位置 |
| `eye_height_bias` | `[-1, 1]` | 眼睛在脸上的高低 | 左右眼骨位置和修正 |
| `eye_tilt_bias` | `[-1, 1]` | 眼裂内外倾斜 | 眼眶 Shape Key |
| `iris_size_bias` | `[-1, 1]` | 虹膜大小 | Shader/眼球 UV |
| `pupil_size_bias` | `[-1, 1]` | 静态瞳孔基准 | Shader；动态收缩另行叠加 |
| `eyelid_fold` | `[0, 1]` | 从无褶皱到明显双眼皮 | Shape Key |
| `upper_lid_openness_bias` | `[-1, 1]` | 中性状态上眼皮开合 | Shape Key |

`eyelid_fold` 是连续参数，不使用单眼皮/双眼皮布尔开关。眨眼和情绪表情使用
另一套表达 Shape Key，不能覆盖身份眼皮参数。

### 6.3 鼻、嘴和眉眼

| 字段 | 范围 | 含义 | 推荐实现 |
|---|---:|---|---|
| `nose_width_bias` | `[-1, 1]` | 鼻子宽度 | Shape Key |
| `nose_height_bias` | `[-1, 1]` | 鼻子高度 | Shape Key |
| `nose_projection_bias` | `[-1, 1]` | 鼻子向前突出 | Shape Key |
| `mouth_width_bias` | `[-1, 1]` | 中性嘴宽 | Shape Key |
| `mouth_height_bias` | `[-1, 1]` | 嘴部垂直位置 | Shape Key |
| `mouth_curve_bias` | `[-1, 1]` | 中性嘴角略下垂到略上扬 | Shape Key |
| `brow_height_bias` | `[-1, 1]` | 眉弓或眼上轮廓高度 | Shape Key/面部骨 |
| `brow_angle_bias` | `[-1, 1]` | 眉眼轮廓角度 | Shape Key/面部骨 |

`mouth_curve_bias` 只能影响中性静态轮廓，不能替代表情系统的开心或难过动作。

## 7. 耳朵、尾巴和物种特征

以下参数语义公共，但允许物种声明不支持：

| 字段 | 范围 | 推荐实现 |
|---|---:|---|
| `ear_size_bias` | `[-1, 1]` | 耳骨统一缩放和耳部修正 Shape Key |
| `ear_width_bias` | `[-1, 1]` | 耳部 Shape Key |
| `ear_tilt_bias` | `[-1, 1]` | 左右耳骨旋转 |
| `ear_droop` | `[0, 1]` | 耳骨姿态和折耳修正 Shape Key |
| `ear_asymmetry` | `[-1, 1]` | 左右耳小范围差异 |
| `tail_length_bias` | `[-1, 1]` | 尾骨链长度比例 |
| `tail_thickness_bias` | `[-1, 1]` | 尾巴 Shape Key |

物种私有参数放在 `species_traits` 下，不污染公共字段。例如：

```json
{
  "species_traits": {
    "fox": {
      "black_leg_coverage": 0.62,
      "tail_tip_coverage": 0.48,
      "cheek_ruff_bias": 0.35
    },
    "dog": {
      "jowl_fullness_bias": -0.12,
      "ear_fold_bias": 0.40,
      "tail_curl_bias": 0.22
    }
  }
}
```

## 8. 毛发轮廓参数

第一版使用可控的网格轮廓、毛片或有限模型变体，不依赖高成本实时毛发粒子。

| 字段 | 范围 | 含义 |
|---|---:|---|
| `body_fur_length_bias` | `[-1, 1]` | 全身基础毛长 |
| `head_tuft_bias` | `[-1, 1]` | 头顶毛簇大小 |
| `cheek_ruff_bias` | `[-1, 1]` | 两颊蓬松轮廓 |
| `chest_ruff_bias` | `[-1, 1]` | 胸前围脖毛 |
| `ear_tuft_bias` | `[-1, 1]` | 耳内和耳尖毛 |
| `limb_feathering_bias` | `[-1, 1]` | 四肢边缘长毛 |
| `tail_fluff_bias` | `[-1, 1]` | 尾巴蓬松程度 |

如果某个模型没有独立毛片或足够拓扑，必须在物种配置中禁用对应参数，不能
只保留一个无效果的配置字段。

## 9. 毛色、区域和花纹

### 9.1 公共语义区域

每个物种的 UV 和遮罩不同，但至少应映射以下语义区域：

```text
primary_body      身体主色区域
secondary_body    胸腹等副色区域
muzzle            口鼻和下巴
eye_surround      眼周
ear_inner         耳内
ear_tip           耳尖
limb_end          四肢末端
paw               手掌和脚掌
tail_tip          尾尖
nose              鼻子
iris              虹膜
pupil             瞳孔
```

### 9.2 色板参数

个体不保存任意 RGB 主色，而保存物种色板与有限偏移：

| 字段 | 类型 | 含义 |
|---|---|---|
| `palette_id` | 枚举 | 物种允许的基础色系 |
| `primary_hue_shift` | `[-1, 1]` | 主色允许范围内的色相偏移 |
| `primary_saturation_bias` | `[-1, 1]` | 主色饱和度偏移 |
| `primary_value_bias` | `[-1, 1]` | 主色明度偏移 |
| `secondary_value_bias` | `[-1, 1]` | 副色从纯白到奶油/灰白的变化 |
| `eye_color_id` | 枚举 | 物种允许的眼睛色板 |
| `nose_color_id` | 枚举 | 鼻子色板 |

狐狸可提供 `red`、`golden`、`cross`、`silver`、`melanistic`、`pale` 等色板；
狗可提供 `black`、`white`、`cream`、`golden`、`red_brown`、`chocolate`、
`gray` 等色板。色板还必须规定哪些主色、副色和花纹组合合法。

### 9.3 花纹参数

| 字段 | 类型/范围 | 含义 |
|---|---|---|
| `pattern_id` | 枚举 | `solid`、`bicolor`、`tricolor` 等物种花纹 |
| `pattern_coverage_bias` | `[-1, 1]` | 花纹总体覆盖面积 |
| `pattern_scale_bias` | `[-1, 1]` | 斑点或纹理尺度 |
| `pattern_contrast_bias` | `[-1, 1]` | 主副色对比度 |
| `pattern_symmetry` | `[0, 1]` | 从自然不对称到高度对称 |
| `face_mask_coverage_bias` | `[-1, 1]` | 面罩覆盖范围 |
| `chest_patch_coverage_bias` | `[-1, 1]` | 胸前副色面积 |
| `paw_patch_coverage_bias` | `[-1, 1]` | 脚掌或袜套面积 |
| `tail_tip_coverage_bias` | `[-1, 1]` | 尾尖副色长度 |

第一版建议提供两张 RGBA 遮罩：

```text
coat_regions_0.png
R = muzzle
G = chest_and_belly
B = limb_end_and_paw
A = tail_tip

coat_regions_1.png
R = eye_surround
G = ear_tip
B = ear_inner
A = species_reserved
```

程序化斑点或条纹可以另用噪声和 UV 参数生成，但必须被区域遮罩限制，不能
覆盖眼球、鼻子、牙齿等非毛发材质。

## 10. Blender 物种母版交付清单

### 10.1 骨骼比例控制

保留公共 Mixamo 主骨名称和父子层级。比例系统至少要能控制：

- 头部整体比例。
- 颈部长度。
- 上臂和前臂长度，左右保持一致。
- 大腿和小腿长度，左右保持一致。
- 肩宽。
- 手掌和脚掌大小。
- 物种耳骨。
- 3 至 5 节尾骨链。

比例变化必须在公共动画骨骼旋转之外单独应用，不能重命名骨骼或把个体比例
直接烘焙进公共动画。

### 10.2 必需身体 Shape Key

命名使用 ASCII，禁止使用 `Key 1`、`Shape.003` 等无语义名称：

下列每行 `/` 两侧表示两个需要分别创建的实际 Shape Key，而不是名称中的
斜杠。

```text
Body_ChestFullness_Pos / Body_ChestFullness_Neg
Body_WaistWidth_Pos / Body_WaistWidth_Neg
Body_BellyDepth_Pos / Body_BellyDepth_Neg
Body_HipWidth_Pos / Body_HipWidth_Neg
Body_HipDepth_Pos / Body_HipDepth_Neg
Body_ArmThickness_Pos / Body_ArmThickness_Neg
Body_LegThickness_Pos / Body_LegThickness_Neg
Body_NeckThickness_Pos / Body_NeckThickness_Neg
Body_PawFullness_Pos / Body_PawFullness_Neg
```

每个 Shape Key 从 `0` 的中性母版变化到 `1` 的正向极值。负向形态不能依赖
Godot 使用负权重；需要明显负向外形时，制作配对 Shape Key：

```text
Body_ArmThickness_Pos
Body_ArmThickness_Neg
```

解析器将有符号参数拆成：

```text
positive_weight = max(value, 0)
negative_weight = max(-value, 0)
```

### 10.3 必需脸部 Shape Key

```text
Face_SkullWidth_Pos / Face_SkullWidth_Neg
Face_ForeheadHeight_Pos / Face_ForeheadHeight_Neg
Face_ForeheadWidth_Pos / Face_ForeheadWidth_Neg
Face_JawWidth_Pos / Face_JawWidth_Neg
Face_CheekboneWidth_Pos / Face_CheekboneWidth_Neg
Face_CheekFullness_Pos / Face_CheekFullness_Neg
Face_LowerFullness_Pos / Face_LowerFullness_Neg
Face_MuzzleLength_Pos / Face_MuzzleLength_Neg
Face_MuzzleWidth_Pos / Face_MuzzleWidth_Neg
Face_MuzzleHeight_Pos / Face_MuzzleHeight_Neg
Face_EyeSocketSize_Pos / Face_EyeSocketSize_Neg
Face_EyeTilt_Pos / Face_EyeTilt_Neg
Face_EyelidFold
Face_UpperLidOpen_Pos / Face_UpperLidOpen_Neg
Face_NoseWidth_Pos / Face_NoseWidth_Neg
Face_NoseHeight_Pos / Face_NoseHeight_Neg
Face_NoseProjection_Pos / Face_NoseProjection_Neg
Face_MouthWidth_Pos / Face_MouthWidth_Neg
Face_MouthHeight_Pos / Face_MouthHeight_Neg
Face_MouthCurve_Pos / Face_MouthCurve_Neg
Face_BrowHeight_Pos / Face_BrowHeight_Neg
Face_BrowAngle_Pos / Face_BrowAngle_Neg
```

不要求第一版一次制作全部配对项。物种配置只能声明已完成并通过验收的参数。
对头像辨识度最高的首批 Shape Key 是：

```text
Face_SkullWidth_Pos / Face_SkullWidth_Neg
Face_CheekFullness_Pos / Face_CheekFullness_Neg
Face_JawWidth_Pos / Face_JawWidth_Neg
Face_MuzzleLength_Pos / Face_MuzzleLength_Neg
Face_MuzzleWidth_Pos / Face_MuzzleWidth_Neg
Face_EyeSocketSize_Pos / Face_EyeSocketSize_Neg
Face_EyeTilt_Pos / Face_EyeTilt_Neg
Face_EyelidFold
Face_NoseWidth_Pos / Face_NoseWidth_Neg
Face_NoseProjection_Pos / Face_NoseProjection_Neg
Face_MouthWidth_Pos / Face_MouthWidth_Neg
Face_ForeheadHeight_Pos / Face_ForeheadHeight_Neg
```

### 10.4 毛发轮廓 Shape Key

```text
Fur_BodyLength
Fur_HeadTuft
Fur_CheekRuff
Fur_ChestRuff
Fur_EarTuft
Fur_LimbFeathering
Fur_TailFluff
```

只有实际移动了网格或毛片的 Shape Key 才能导出。没有可变毛发几何时，先
禁用该参数。

### 10.5 自动修正 Shape Key

以下修正项由运行时根据参数组合自动计算，不进入个体随机基因：

```text
Corrective_LargeEye_Eyelid
Corrective_NarrowFace_EyeContainment
Corrective_FullCheek_Mouth
Corrective_LargeHead_Neck
Corrective_LargeBelly_Waist
Corrective_WideShoulder_ArmRoot
Corrective_LongMuzzle_Nose
Corrective_DroopEar_EarRoot
```

修正权重示例：

```text
LargeEyeEyelid = max(0, eye_size_bias - 0.65)
FullCheekMouth = max(0, cheek_fullness_bias) * max(0, mouth_width_bias)
LargeHeadNeck  = max(0, head_torso_bias) * max(0, -neck_thickness_bias)
```

### 10.6 Shape Key 制作规则

- 所有身份 Shape Key 必须相对于同一个 `Basis`。
- 创建 Shape Key 后不得改变网格顶点数量或顶点顺序。
- 身份 Shape Key 不得包含表情，例如笑、皱眉或眨眼。
- 左右对称参数必须同时编辑两侧；不对称参数单独命名 `_L`、`_R`。
- 眼球、牙齿和舌头等独立网格要同步验证，不能被脸部网格包住。
- 每个单独 Shape Key 和允许的组合都要检查正面、侧面和四分之三视角。
- 极值必须仍然自然；不要把雕刻极限直接作为运行时极值。
- 导出前确认 glTF 包含 morph target 名称。

## 11. 物种配置契约

每个物种需要一个版本化配置，示意结构如下：

```json
{
  "schema_version": 1,
  "species": "fox",
  "profile_version": 1,
  "model_path": "res://characters/fox/fox.glb",
  "ranges": {
    "head_torso_ratio": {"min": 0.42, "base": 0.48, "max": 0.55},
    "neck_torso_ratio": {"min": 0.10, "base": 0.14, "max": 0.18}
  },
  "morph_map": {
    "body_bias.belly_depth_bias": {
      "positive": "Body_BellyDepth_Pos",
      "negative": "Body_BellyDepth_Neg"
    },
    "face.cheek_fullness_bias": {
      "positive": "Face_CheekFullness_Pos",
      "negative": "Face_CheekFullness_Neg"
    }
  },
  "bone_map": {
    "head_scale": ["mixamorig:Head"],
    "neck_length": ["mixamorig:Neck"],
    "arm_length_left": ["mixamorig:LeftArm", "mixamorig:LeftForeArm"],
    "arm_length_right": ["mixamorig:RightArm", "mixamorig:RightForeArm"]
  },
  "fat_influence": {
    "arms": 0.75,
    "legs": 0.80,
    "belly": 0.90,
    "face": 0.65,
    "neck": 0.70
  },
  "palettes": ["red", "golden", "cross", "silver", "melanistic", "pale"],
  "patterns": ["classic", "bicolor", "cross", "face_mask"]
}
```

已经被领养的精灵必须保存 `profile_version`。发布新物种配置时不得直接改变
旧版本含义，否则同一精灵升级后会换脸。可选择保留旧配置，或通过明确迁移
生成并保存新的解析后参数。

## 12. 个体 AppearanceGenome v1

建议的持久化结构：

```json
{
  "schema_version": 1,
  "species": "fox",
  "profile_version": 1,
  "seed": 18427,
  "macro": {
    "stature_z": 0.32,
    "frame_size_z": 0.18,
    "body_fat_z": 1.10,
    "muscularity_z": -0.20
  },
  "proportions": {
    "head_torso_bias": 0.25,
    "neck_torso_bias": -0.10,
    "arm_torso_bias": 0.05,
    "leg_torso_bias": -0.18,
    "shoulder_torso_bias": 0.12,
    "hand_arm_bias": 0.03,
    "paw_leg_bias": 0.20
  },
  "body_bias": {
    "chest_fullness_bias": 0.12,
    "waist_width_bias": 0.08,
    "belly_depth_bias": 0.35,
    "hip_width_bias": 0.05,
    "hip_depth_bias": 0.10,
    "arm_thickness_bias": -0.12,
    "leg_thickness_bias": 0.04,
    "neck_thickness_bias": -0.05,
    "paw_fullness_bias": 0.18
  },
  "face": {
    "skull_width_bias": 0.22,
    "forehead_height_bias": 0.15,
    "forehead_width_bias": 0.05,
    "jaw_width_bias": -0.10,
    "cheekbone_width_bias": 0.08,
    "cheek_fullness_bias": 0.30,
    "lower_face_fullness_bias": 0.16,
    "muzzle_length_bias": -0.12,
    "muzzle_width_bias": 0.10,
    "muzzle_height_bias": 0.02,
    "eye_size_bias": 0.28,
    "eye_spacing_bias": -0.06,
    "eye_height_bias": 0.05,
    "eye_tilt_bias": 0.14,
    "iris_size_bias": 0.12,
    "pupil_size_bias": -0.04,
    "eyelid_fold": 0.72,
    "upper_lid_openness_bias": -0.08,
    "nose_width_bias": 0.10,
    "nose_height_bias": -0.02,
    "nose_projection_bias": 0.06,
    "mouth_width_bias": 0.04,
    "mouth_height_bias": 0.00,
    "mouth_curve_bias": 0.05,
    "brow_height_bias": 0.02,
    "brow_angle_bias": -0.06
  },
  "appendages": {
    "ear_size_bias": 0.18,
    "ear_width_bias": -0.08,
    "ear_tilt_bias": 0.12,
    "ear_droop": 0.05,
    "ear_asymmetry": -0.08,
    "tail_length_bias": 0.14,
    "tail_thickness_bias": 0.10
  },
  "fur": {
    "body_fur_length_bias": 0.06,
    "head_tuft_bias": 0.10,
    "cheek_ruff_bias": 0.28,
    "chest_ruff_bias": 0.22,
    "ear_tuft_bias": 0.12,
    "limb_feathering_bias": -0.04,
    "tail_fluff_bias": 0.36
  },
  "coat": {
    "palette_id": "red",
    "pattern_id": "classic",
    "primary_hue_shift": -0.08,
    "primary_saturation_bias": 0.12,
    "primary_value_bias": -0.04,
    "secondary_value_bias": 0.10,
    "eye_color_id": "amber",
    "nose_color_id": "black",
    "pattern_coverage_bias": 0.06,
    "pattern_scale_bias": -0.10,
    "pattern_contrast_bias": 0.14,
    "pattern_symmetry": 0.78,
    "face_mask_coverage_bias": -0.04,
    "chest_patch_coverage_bias": 0.15,
    "paw_patch_coverage_bias": 0.08,
    "tail_tip_coverage_bias": 0.22
  },
  "species_traits": {}
}
```

字段可以多于当前物种实际支持的参数，但解析器只能应用配置中明确声明的
字段。未支持字段必须记录为禁用，不能静默假装已经产生外观变化。

## 13. 随机生成流程

```text
1. 根据 seed 初始化确定性随机数生成器
2. 采样 stature、frame_size、body_fat、muscularity 宏观潜变量
3. 在物种范围内采样骨架比例偏差
4. 以宏观潜变量为条件采样局部身体偏差
5. 采样脸部结构和五官参数
6. 采样耳朵、尾巴、毛发、色板和花纹
7. 解析物种范围与宏观/局部相关公式
8. 计算自动修正 Shape Key
9. 执行几何和组合约束检查
10. 不合格时按同一 seed 的下一候选序号重采样
11. 应用到物种母版并渲染标准头像与全身图
12. 检查与已有精灵的外貌距离
13. 保存 genome、profile_version 和标准照片
```

宏观变量使用截断正态分布。局部偏差的标准差必须明显小于宏观变量，避免
频繁产生只胖肚子、只胖脸或粗躯干细四肢的个体。

## 14. 几何与组合约束

至少实现以下约束：

### 14.1 身体比例

- 手臂、腿、头和颈只能落在物种配置范围内。
- 左右手臂和左右腿的长度默认一致。
- 手臂和腿的相对长度不能超过物种允许的 `arm_leg_ratio`。
- 头部变大时，颈部最小粗细和肩宽下限同步提高。
- 腹部和腰部极端变化时，不能穿过手臂中性姿态或腿根。

### 14.2 五官包含关系

```text
eye_spacing / 2 + eye_width / 2 <= face_half_width - eye_margin
nose_width <= muzzle_width * species_nose_muzzle_limit
mouth_width <= face_width * species_mouth_face_limit
forehead_height + muzzle_height <= usable_face_height
```

- 眼球不能露出眼眶或穿过眼皮。
- 鼻子不能超出口鼻部支持范围。
- 嘴角不能在脸颊丰满时陷入网格。
- 耳根必须留在头骨范围内。
- 牙齿和舌头不能在中性闭嘴状态穿出嘴部。

### 14.3 宏观体型一致性

- 极端肥胖时所有主要软组织部位保持正向增长。
- 极端消瘦时大多数主要软组织部位保持负向变化。
- 肌肉主要影响肩胸和四肢，不显著放大腹部。
- 骨架粗壮主要影响肩、胸腔、髋和关节，不等同于脂肪。

### 14.4 自动验收

- 检查所有骨骼比例、Shape Key 权重和 Shader 参数均在范围内。
- 检查角色包围盒、脚底高度和眼球位置。
- 渲染正面、侧面、四分之三和全身标准视图。
- 第一版使用参数向量距离避免重复；后续使用 DINOv2 或 CLIP 图像特征检查
  标准头像是否过于相似。
- 任何几何异常、约束失败或相似度过高的候选重新生成。

## 15. 头像辨识度规则

随机参数不等于可辨认身份。每只精灵至少需要 3 至 5 个明显身份锚点：

- 一个脸型特征，例如宽脸、窄下巴或明显婴儿肥。
- 一个眼睛特征，例如大眼、眼距、眼角倾斜或虹膜颜色。
- 一个耳朵轮廓特征，例如大小、倾斜、下垂或轻微不对称。
- 一个面部毛色或花纹特征。
- 一个可选的鼻子、口鼻、额头或局部标记特征。

外貌距离建议权重：

```text
脸型和五官       0.50
面部花纹和颜色   0.30
耳朵轮廓         0.15
身体比例         0.05
```

身高和三围不能承担头像辨识任务。

## 16. Godot 运行时接入要求

仅在 Blender 添加 Shape Key 并重新导出 GLB，还不能自动完成外貌系统。完整
接入还需要：

1. Godot 导入后确认 GLB 保留所有 morph target 名称。
2. 为每个物种创建 `SpeciesAppearanceProfile` 资源或结构化配置。
3. 实现 `AppearanceResolver`，把 genome 解析成实际比例和权重。
4. 实现 `AppearanceApplicator`：
   - 调用 `MeshInstance3D.set_blend_shape_value()`。
   - 应用骨骼比例层，但不修改公共动画骨名和层级。
   - 为每个实例复制或参数化材质，设置毛色和花纹。
   - 应用自动修正 Shape Key。
5. 同步更新角色的骨骼碰撞体、附件插槽和摄像机关注高度。
6. 保存并加载 `AppearanceGenome`、`profile_version` 和标准照片。
7. 在待机、行走、跑步、转身和表情动画中验证所有极值组合。

身份 Shape Key 是持续存在的基础外貌；眨眼、说话、开心等表情 Shape Key
在它们之上叠加，不能互相覆盖。

## 17. 狗和狐狸升级顺序

当前 dog 和 fox GLB 已有蒙皮骨架，但还没有 morph target。建议先只升级狐狸，
完成以下最小闭环：

### 第一阶段：狐狸最小可辨识母版

- 保留公共 Mixamo 骨架层级。
- 修正尾巴为 3 至 5 节骨链。
- 建立头、颈、手臂、腿和肩宽比例控制。
- 制作 9 组身体 Shape Key：胸、腰、腹、臀宽、臀深、胳膊、腿、颈、脚掌。
- 制作 12 个高辨识度脸部 Shape Key。
- 制作耳朵大小、倾斜和轻微不对称控制。
- 制作主色、副色、眼周、耳尖、脚掌和尾尖遮罩。
- 提供至少 4 个狐狸色板和 3 个花纹。
- 导出 GLB，并确认 morph target 名称完整。

### 第二阶段：狐狸自动生成验证

- 实现物种配置和外貌应用器。
- 固定相机生成 50 至 100 个正面头像和全身图。
- 检查是否存在比例异常、穿模或大量相似脸。
- 调整参数范围、相关系数和修正 Shape Key。
- 通过后冻结 `fox profile_version = 1`。

### 第三阶段：迁移到狗

- 狗使用相同公共参数名。
- 根据狗的网格重新制作 Shape Key，不能复制狐狸顶点数据。
- 建立狗自己的范围、脂肪影响系数、色板和花纹。
- 使用同一生成器和验收流程验证。

## 18. Blender 交付验收

- [ ] `.blend` 保留中性 `Basis`、骨架、所有 Shape Key 和遮罩源文件。
- [ ] 公共骨名称和父子层级未改变。
- [ ] 头、颈、手臂、腿和肩宽比例能在安全范围内变化。
- [ ] 身体与脸部必需 Shape Key 命名符合规范。
- [ ] 正负配对 Shape Key 的方向正确。
- [ ] 极端胖瘦时四肢、腹部、颈部和脸部仍协调。
- [ ] 大眼、窄脸、丰满脸颊等组合已有修正项。
- [ ] 眼球、眼皮、鼻子、嘴、牙齿没有穿模。
- [ ] 毛色遮罩区域边界清楚，无错误覆盖。
- [ ] GLB 重新导入 Blender 后仍包含骨架、蒙皮、贴图和 morph target。
- [ ] Godot 导入后能按名称找到每个 morph target。
- [ ] 公共动作播放时身份外貌保持不变。

## 19. 第一版参数规模

完整公共协议约有 70 至 80 个可持久化字段；狐狸第一版只需启用其中 45 至
55 个。字段数量不等于需要同样数量的人工 Shape Key：

```text
骨架比例参数       约 8 个     -> 骨骼比例层
身体轮廓参数       约 9 个     -> 8 至 12 个 Shape Key
脸部身份参数       约 26 个    -> 12 至 24 个首批 Shape Key，逐步扩充
耳朵和尾巴参数     约 8 个     -> 骨骼加少量 Shape Key
毛发轮廓参数       约 7 个     -> 可选 Shape Key/模型层
颜色和花纹参数     约 15 个    -> Shader、色板和遮罩
自动修正参数       不持久化    -> 6 至 10 个 corrective Shape Key
```

不要求首个狐狸版本一次实现全部字段。公共协议可以先完整定义，物种配置只
启用已经制作和验收的参数。这样后续增加 Shape Key 时不需要重新设计数据
结构。

最后更新：2026-07-18
