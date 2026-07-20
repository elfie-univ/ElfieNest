# Blender 动物外貌母版制作教程

本文面向已经完成基础模型、骨架和蒙皮的拟人化动物角色，说明如何把一个
中性角色制作成可以配置高矮、胖瘦、脸型、五官、毛色和花纹的物种母版。

本文是 Blender 实际操作手册。参数含义、随机分布、Godot 数据结构和物种
范围见 [外貌参数与物种母版规范](APPEARANCE_SYSTEM_SPEC.md)。从图片生成
模型、Mixamo 绑定、尾骨和 Godot 集成见
[角色创建与集成手册](CHARACTER_CREATION_GUIDE.md)。

## 1. 先理解最终结构

不要把所有外貌参数都做成 Shape Key。正式母版由四类控制共同组成：

| 控制类型 | 负责内容 | 是否需要雕刻 |
|---|---|---|
| 骨骼比例 | 身高、头身比、颈长、臂长、腿长、肩宽、手脚大小 | 否，但要逐动作验收 |
| Shape Key | 胸腰腹臀、四肢粗细、脸型、口鼻和眼皮轮廓 | 是，每个物种制作一次 |
| 材质遮罩 | 主毛色、副毛色、眼周、耳尖、爪子和尾尖 | 否，主要是绘制遮罩 |
| 独立部件和挂件 | 眼球、眼镜、帽子、衣服、毛簇变体 | 视部件而定 |

每只精灵不会重新雕刻。狐狸只制作一套狐狸母版，狗只制作一套狗母版；
运行时把不同参数混合到同一母版上。

当前 `fox_morph_prototype.blend` 中按空间椭球自动生成的 Shape Key 只用于
证明 glTF morph target 链路可用。它没有可靠的语义区域，可能误动耳朵、
头皮或其他相邻部位，不能作为正式美术母版继续叠加。

## 2. 开工前的硬性规则

1. 使用完成绑骨时保存的原始 `.blend`，不要优先使用重新导入 GLB 后骨骼
   显示异常的文件。
2. 保存副本，例如 `fox_appearance_master_v001.blend`，不得覆盖唯一源文件。
3. 参考姿态必须是中性 T-Pose 或 A-Pose，不得保留 Action 或 NLA 动画。
4. 在创建第一个 Shape Key 前完成网格分离、合并、重拓扑和减面。
5. 创建 `Basis` 后禁止增加、删除、合并、细分顶点，也不能改变顶点顺序。
6. 不修改公共 Mixamo 骨骼名称和父子层级。
7. 左右对称参数默认一起变化；不对称参数明确使用 `_L` 和 `_R`。
8. 每完成一个参数立即检查正面、侧面、四分之三视角和一个公共动作。

## 3. 推荐的对象结构

在 Blender 的 Outliner 中整理为以下结构。对象可以因模型实际情况减少，但
不能把眼球和眼眶皮肤当成同一个语义区域处理。

```text
CHARACTER
├── Armature
├── Body                  # 头、躯干、四肢和尾巴主蒙皮网格
├── Eye_L                 # 能分离时使用独立眼球
├── Eye_R
├── Teeth                 # 存在时独立
├── Tongue                # 存在时独立
├── HairOrFurCards        # 存在独立毛片时使用
├── Outfit                # 服装独立蒙皮网格
└── Accessories           # 眼镜、帽子等刚性挂件
```

### 3.1 判断眼球能否独立

1. 选中身体网格，按 `Tab` 进入 Edit Mode。
2. 鼠标悬停在一只眼球上，按 `L` 执行 Select Linked。
3. 如果只选中完整眼球而没有选中眼皮、头皮或耳朵，说明它是独立拓扑岛。
4. 在创建 Shape Key 之前，可以按 `P -> Selection` 分离成 `Eye_L` 或
   `Eye_R`。
5. 如果按 `L` 会连带选中整张脸，不要强行分离；改用眼眶顶点组和材质遮罩。

如果眼睛只是画在身体贴图上，没有独立眼球几何，“眼球大小”和“虹膜大小”
应通过材质或 UV 实现，不能用一个空间范围直接推头部顶点。

## 4. 必须创建的语义区域

语义区域使用普通 Vertex Group，不用于蒙皮，因此名称不得与骨骼重名。
统一使用 `REGION_` 前缀。保护区使用 `LOCK_` 前缀。

### 4.1 身体区域

| Vertex Group | 应包含 | 必须排除 | 主要用途 |
|---|---|---|---|
| `REGION_Chest` | 锁骨下方到肋骨下缘 | 肩关节、腋窝、腹部 | 胸宽和胸厚 |
| `REGION_Waist` | 肋骨下缘到骨盆上缘 | 胸部、臀部、手臂 | 腰宽和胖瘦过渡 |
| `REGION_Belly` | 腹部正面和侧面软组织 | 背部、胯根、尾根 | 肚子前凸和腹围 |
| `REGION_Hip` | 骨盆两侧和臀部 | 大腿根、尾根 | 臀宽和臀厚 |
| `REGION_Neck` | 头根到肩线之间 | 下颌、胸毛、肩膀 | 颈部粗细和接缝修正 |
| `REGION_UpperArm_L/R` | 肩到肘 | 肩窝和肘关节中心 | 上臂粗细 |
| `REGION_ForeArm_L/R` | 肘到腕 | 肘和腕关节中心 | 前臂粗细 |
| `REGION_Hand_L/R` | 手掌和手指外轮廓 | 前臂 | 手掌肉感 |
| `REGION_Thigh_L/R` | 胯到膝 | 胯根和膝关节中心 | 大腿粗细 |
| `REGION_Calf_L/R` | 膝到踝 | 膝和踝关节中心 | 小腿粗细 |
| `REGION_Foot_L/R` | 脚掌和脚趾 | 小腿 | 脚掌肉感 |
| `REGION_Tail` | 尾根到尾尖全部表面 | 臀部 | 尾巴粗细和毛量 |
| `REGION_TailTip` | 尾巴末端约 20% 至 35% | 尾巴中段 | 尾尖颜色和局部轮廓 |

四肢区域在接近关节时权重应逐渐降低，不能在肘、膝、腕和踝处形成硬切线。

### 4.2 头部和脸部区域

| Vertex Group | 应包含 | 必须排除 | 主要用途 |
|---|---|---|---|
| `REGION_Skull` | 额头、太阳穴、后脑轮廓 | 耳朵、眼球、嘴吻、脖子 | 头骨宽度 |
| `REGION_Forehead` | 眉弓上方到头顶毛发下缘 | 耳根、眼球、头顶毛簇 | 额头高宽 |
| `REGION_Jaw` | 下颌骨和下巴外轮廓 | 嘴唇、脖子、脸颊上部 | 下颌宽度 |
| `REGION_Cheekbone_L/R` | 眼眶外下方的结构轮廓 | 耳朵、眼皮、嘴角 | 颧部宽度 |
| `REGION_CheekSoft_L/R` | 颧部下方到嘴角外侧软组织 | 眼皮、嘴唇、耳毛 | 脸颊肉感 |
| `REGION_LowerFace` | 两颊下缘和下巴周围软组织 | 脖子、嘴内 | 下半脸肉感 |
| `REGION_Muzzle` | 鼻根到嘴部前端的完整口鼻体积 | 眼眶、脸颊、牙齿 | 嘴吻长宽高 |
| `REGION_Nose` | 鼻头和鼻翼 | 口鼻毛发和上唇 | 鼻宽、高和突出度 |
| `REGION_Mouth` | 上下唇及嘴角附近一圈 | 脸颊大面积区域、牙齿 | 嘴宽、高和静态曲线 |
| `REGION_EyeSocket_L/R` | 包围眼球的眼眶皮肤 | 眼球、眉毛、耳朵、头皮 | 眼眶大小和倾斜 |
| `REGION_UpperLid_L/R` | 上眼皮及一圈过渡顶点 | 眉弓、眼球 | 眼皮开合和褶皱 |
| `REGION_LowerLid_L/R` | 下眼皮及一圈过渡顶点 | 脸颊主体、眼球 | 大眼修正和眨眼配合 |
| `REGION_Brow_L/R` | 眉毛或眼上结构轮廓 | 眼皮、头顶毛发 | 眉高和眉角 |
| `REGION_Ear_L/R` | 整只耳朵，从耳根到耳尖 | 头皮、眉弓 | 耳朵大小、宽度和倾斜 |
| `REGION_EarInner_L/R` | 耳内可见区域 | 耳背、头皮 | 耳内颜色 |
| `REGION_EarTip_L/R` | 耳尖约 15% 至 25% | 耳中段 | 耳尖颜色和毛簇 |

眼眶左右必须分组。一个覆盖双眼和整块额头的圆形选区不合格，因为它会误动
头皮、耳根和另一侧面部。

### 4.3 毛发轮廓区域

只有模型存在独立毛片、毛簇或足够厚度的毛发几何时才建立：

| Vertex Group | 应包含 | 主要用途 |
|---|---|---|
| `REGION_HeadTuft` | 头顶独立毛簇 | 头顶毛量 |
| `REGION_CheekRuff_L/R` | 两颊外轮廓长毛 | 脸颊蓬松度 |
| `REGION_ChestRuff` | 胸前围脖毛 | 胸毛长度和宽度 |
| `REGION_EarTuft_L/R` | 耳内和耳尖毛簇 | 耳毛长度 |
| `REGION_LimbFeathering_L/R` | 四肢后缘长毛 | 四肢饰毛长度 |
| `REGION_TailFluff` | 尾巴外层毛发轮廓 | 尾巴蓬松度 |

如果所谓“毛发”只是身体贴图，不要建立这些组，也不要创建无效果的毛发
Shape Key。

### 4.4 保护区域

保护区域用于检查和排除，不参与最终随机参数。

```text
LOCK_EyeBall_L
LOCK_EyeBall_R
LOCK_Teeth
LOCK_Tongue
LOCK_MouthInterior
LOCK_EarRoot_L
LOCK_EarRoot_R
LOCK_NeckSeam
LOCK_ShoulderJoint_L
LOCK_ShoulderJoint_R
LOCK_ElbowJoint_L
LOCK_ElbowJoint_R
LOCK_HipJoint_L
LOCK_HipJoint_R
LOCK_KneeJoint_L
LOCK_KneeJoint_R
LOCK_TailRoot
```

如果眼球、牙齿或舌头是独立对象，不必重复建立同名 Vertex Group，但必须在
每个脸部 Shape Key 验收时显示这些对象检查穿模。

### 4.5 毛色和花纹区域

这些区域最终应绘制到 RGBA 遮罩贴图，不要求都保留为 Vertex Group。制作
遮罩前可先用同名区域辅助选面。

```text
COAT_PrimaryBody
COAT_SecondaryBody
COAT_Muzzle
COAT_EyeSurround
COAT_EarInner
COAT_EarTip
COAT_LimbEnd
COAT_Paw
COAT_TailTip
COAT_Nose
COAT_Iris
COAT_Pupil
```

狐狸至少要区分主红色、胸腹副色、口鼻、眼周、耳尖、四肢末端和尾尖。狗
至少要区分身体主色、胸腹、口鼻、眼周、耳朵、四肢和可变斑块区域。

## 5. 在 Blender 中建立一个 Vertex Group

以下步骤对所有 `REGION_` 和 `LOCK_` 组重复执行。

1. 选中 `Body`，保持 Object Mode。
2. 在右侧 Properties 点击绿色倒三角，进入 Object Data Properties。
3. 展开 Vertex Groups，点击 `+` 创建组并按本文名称重命名。
4. 按 `Tab` 进入 Edit Mode，按 `Alt + A` 清空选择。
5. 打开 X-Ray，Mac 使用 `Option + Z`，其他平台使用 `Alt + Z`。
6. 使用框选、圈选或鼠标悬停后按 `L` 选中目标区域。
7. 在 Vertex Group 面板把 Weight 设为 `1.000`，点击 Assign。
8. 对误选区域执行 Remove，而不是把错误顶点留在组内。
9. 切换到 Weight Paint，用 Smooth 让区域边缘形成窄而连续的渐变。
10. 回到 Edit Mode，点击该组的 Select，旋转检查正面、侧面和背面。

组内核心区域使用 `1.0`；过渡边缘可以从 `0.8`、`0.5` 平滑下降到 `0`。
眼皮、嘴角和关节过渡区不要使用一圈突然从 `1` 变成 `0` 的硬边。

### 5.1 每个区域的验收方法

1. 在 Edit Mode 清空选择。
2. 选中目标 Vertex Group，点击 Select。
3. 按 `H` 暂时隐藏选中顶点。
4. 检查是否有本应属于该区域的洞或漏选。
5. 按 `Option/Alt + H` 恢复显示。
6. 再选择相邻保护组，确认二者没有大面积重叠。

`REGION_EyeSocket_L` 的合格标准是：只覆盖左眼周围皮肤，不能选择左耳、
头顶、右眼、眼球或大片脸颊。区域不合格时禁止开始制作眼睛 Shape Key。

## 6. 骨骼比例参数

骨骼比例负责长度和整体比例，不使用 Shape Key 直接拉长整个角色。

| 参数 | Mixamo 基础映射 | 首次校准建议范围 |
|---|---|---:|
| 整体身高 | 角色 VisualRoot 或完整骨架 | `0.90 - 1.10` |
| 头部整体比例 | `mixamorig:Head` | `0.92 - 1.08` |
| 颈部长度 | `mixamorig:Neck` | `0.90 - 1.10` |
| 手臂长度 | `Left/RightArm`、`Left/RightForeArm` | `0.94 - 1.06` |
| 腿部长度 | `Left/RightUpLeg`、`Left/RightLeg` | `0.94 - 1.06` |
| 肩宽 | `Left/RightShoulder` 的横向位置 | `0.94 - 1.06` |
| 手掌大小 | `Left/RightHand` | `0.92 - 1.08` |
| 脚掌大小 | `Left/RightFoot`、`Left/RightToeBase` | `0.92 - 1.08` |

这些数值只是开始测试的安全范围，不是所有物种的最终范围。

### 6.1 在 Blender 中测试骨骼比例

1. 保存副本，选中 `Armature` 并进入 Pose Mode。
2. 在 Bone Properties 中确认要测试的骨骼名称。
3. 把 Transform Orientation 设置为 Local。
4. 长度变化只调整骨骼本地长度轴；Mixamo 骨骼通常以本地 Y 为长度轴。
5. 左右对应骨骼输入相同数值，不靠肉眼分别拖动。
6. 播放 `idle`、`walking`、`running` 和一个手臂幅度较大的动作。
7. 记录不滑脚、不脱臼、不塌陷的最小值和最大值。
8. 使用 `Alt/Option + G`、`Alt/Option + R`、`Alt/Option + S` 清除测试姿态。

不要执行 Apply Pose as Rest Pose，也不要为每只精灵改写骨架。Blender 中只
负责校准安全范围；Godot 运行时在动画结果之上应用个体比例层。

### 6.2 需要配套修正的比例

- 大头需要 `Corrective_LargeHead_Neck` 修正颈部接缝。
- 宽肩需要 `Corrective_WideShoulder_ArmRoot` 修正腋下和肩根。
- 手脚放大后需要检查腕、踝连接处。
- 腿长变化后需要同步角色高度、脚底位置和主碰撞体。

## 7. 创建 Shape Key 的统一流程

### 7.1 创建 Basis

1. 选中 `Body`，进入 Object Data Properties。
2. 找到 Shape Keys，点击 `+`，生成 `Basis`。
3. 再点击 `+` 创建第一个形态并立即重命名。
4. 所有身份 Shape Key 的 Relative To 必须保持为 `Basis`。
5. 每个 Shape Key 的 Value 保持 `0.0`，只有检查时临时改为 `1.0`。

### 7.2 只修改指定区域

1. 把所有 Shape Key 设为 `0`。
2. 选中目标 Shape Key，例如 `Face_CheekFullness_Pos`。
3. 进入 Edit Mode，在 Vertex Groups 中选择 `REGION_CheekSoft_L` 和
   `REGION_CheekSoft_R`。
4. 隐藏其余顶点，或使用 Sculpt Mode 的 Mask 保护非目标区域。
5. 打开 X Mirror；模型本身不完全对称时分别小幅修正左右两侧。
6. 使用 Grab 调轮廓、Inflate 调肉感、Smooth 清除折痕。
7. 不使用会增加或删除顶点的工具。
8. 回到 Object Mode，在 `0` 和 `1` 之间反复切换检查。

禁止仅凭三维空间半径自动选择。空间上靠得近不代表语义相同：眼眶可能靠近
耳根，手臂可能靠近腹部，尾巴可能靠近腿部。

### 7.3 正负形态

每个有符号参数使用两个独立 Shape Key：

```text
Face_SkullWidth_Pos   # Value 0 到 1：从中性到宽头
Face_SkullWidth_Neg   # Value 0 到 1：从中性到窄头
```

后续表格中的 `Face_SkullWidth_Pos/Neg` 是文档简写，实际必须分别创建
`Face_SkullWidth_Pos` 和 `Face_SkullWidth_Neg`。Shape Key 名称中不能包含
斜杠，也不能只创建其中一个后依赖负权重。

不要依赖运行时使用负权重，也不要同时打开同一参数的 `Pos` 和 `Neg`。

## 8. 第一阶段必须完成的 Shape Key

第一阶段目标是获得明显但自然的身份差异。先完成本节，通过验收后再进入
第二阶段。

### 8.1 身体形态

| Shape Key | 使用区域 | 雕刻目标 | 不能改变 |
|---|---|---|---|
| `Body_ChestFullness_Pos/Neg` | `REGION_Chest` | 胸腔宽度和前后厚度 | 肩关节和腹部 |
| `Body_WaistWidth_Pos/Neg` | `REGION_Waist` | 腰部横向宽度 | 胸和臀 |
| `Body_BellyDepth_Pos/Neg` | `REGION_Belly` | 腹部向前突出或收平 | 背部、胯根、手臂 |
| `Body_HipWidth_Pos/Neg` | `REGION_Hip` | 骨盆和臀部横向宽度 | 大腿根和尾根 |
| `Body_ArmThickness_Pos/Neg` | 四个手臂区域 | 围绕各自骨轴均匀增减 | 肩、肘、腕中心 |
| `Body_LegThickness_Pos/Neg` | 四个腿部区域 | 围绕各自骨轴均匀增减 | 胯、膝、踝中心 |
| `Body_NeckThickness_Pos/Neg` | `REGION_Neck` | 颈围和头肩过渡 | 下颌和胸毛 |
| `Body_PawFullness_Pos/Neg` | 手掌和脚掌区域 | 掌部肉感和轮廓 | 腕、踝和手指长度 |

`Body_Fat` 不作为一个粗暴的全身 Shape Key。运行时的 `body_fat_z` 同时驱动
胸、腰、腹、四肢、颈部和脸颊，各部位仍保留小范围局部偏差。

### 8.2 高辨识度脸部形态

| Shape Key | 使用区域 | 雕刻目标 | 不能改变 |
|---|---|---|---|
| `Face_SkullWidth_Pos/Neg` | `REGION_Skull` | 太阳穴和后脑宽度 | 耳朵、眼球和嘴吻 |
| `Face_ForeheadHeight_Pos/Neg` | `REGION_Forehead` | 眉弓到头顶的有效高度 | 耳尖和头顶毛簇 |
| `Face_JawWidth_Pos/Neg` | `REGION_Jaw` | 下颌和下巴宽度 | 脖子和嘴唇 |
| `Face_CheekFullness_Pos/Neg` | 两侧脸颊软组织 | 婴儿肥或收瘦 | 眼皮、嘴角和耳毛 |
| `Face_MuzzleLength_Pos/Neg` | `REGION_Muzzle` | 沿面部前向改变口鼻长度 | 眼眶和鼻头相对位置 |
| `Face_MuzzleWidth_Pos/Neg` | `REGION_Muzzle` | 口鼻横向宽度 | 鼻翼比例和脸颊 |
| `Face_EyeSocketSize_Pos/Neg` | 左右眼眶组 | 眼皮包围圈大小 | 眼球、头皮、耳朵 |
| `Face_EyeTilt_Pos/Neg` | 左右眼眶和眼皮 | 内外眼角倾斜 | 眉毛和眼球中心 |
| `Face_NoseWidth_Pos/Neg` | `REGION_Nose` | 鼻翼和鼻头宽度 | 口鼻主体 |
| `Face_NoseProjection_Pos/Neg` | `REGION_Nose` | 鼻头向前突出程度 | 整个嘴吻长度 |
| `Face_MouthWidth_Pos/Neg` | `REGION_Mouth` | 两侧嘴角间距 | 脸颊主体和表情 |
| `Face_EyelidFold` | 上眼皮组 | 从无褶皱到明显褶皱 | 眼睛开合和眉毛 |

### 8.3 眼睛大小的正确做法

眼睛大小不是单独把 `REGION_EyeSocket` 向外推：

1. 独立 `Eye_L` 和 `Eye_R` 以各自中心等比缩放。
2. `Face_EyeSocketSize_Pos/Neg` 只调整眼眶和眼皮包围圈。
3. `Corrective_LargeEye_Eyelid` 负责大眼极值时让眼皮继续包住眼球。
4. 眼距和眼睛高低优先使用眼球骨或独立对象位置，不拉伸整块脸皮。
5. 虹膜和瞳孔大小使用材质参数，不缩放头部网格。

如果模型没有独立眼球，也没有可分离眼球拓扑，第一版先禁用眼球大小，只做
眼眶轮廓、眼角倾斜和眼睛颜色。

### 8.4 完整示例：制作肚子大小

以下示例制作 `Body_BellyDepth_Pos`，不要直接在全身网格上使用 Inflate：

1. 确认 `REGION_Belly` 只包含腹部正面和侧面，不包含背部、手臂、胯根和
   尾根。
2. 所有 Shape Key 设为 `0`，点击 `+` 新建并命名
   `Body_BellyDepth_Pos`。
3. 选中该 Shape Key，进入 Edit Mode，通过 Vertex Group 选择
   `REGION_Belly`。
4. 隐藏未选择顶点，然后切换侧面视图。先确认角色前方轴向，不要凭固定
   XYZ 猜测。
5. 使用 Proportional Editing 或 Sculpt Grab，把腹部中心缓慢向前移动。
6. 使用 Inflate 轻微增加腹部两侧厚度，背部轮廓保持不动。
7. 腰、胯和胸的交界只做小幅平滑过渡，不能形成球形硬鼓包。
8. 回到 Object Mode，在 `0` 和 `1` 之间切换并播放走路动作。
9. 如果手臂中性姿态穿进腹部，先减小极值，不用移动手臂来掩盖问题。
10. 从中性 `Basis` 重新创建 `Body_BellyDepth_Neg`，将腹部自然收平；不要
    复制正向形态后简单反向缩放。

合格结果是腰腹连续、侧面差异明显、正面略有围度变化。像独立气球一样的
圆形肚子、背部同时鼓起或胯根被拉长都不合格。

### 8.5 完整示例：制作眼睛大小

如果有独立眼球，先处理眼球，再处理眼眶：

1. 选择 `Eye_L`，把 Object Origin 设置在左眼球几何中心；`Eye_R` 同样处理。
2. 保持两个眼球对象的对象级 Scale 为 `1, 1, 1`，记录中性尺寸。
3. 在测试副本中分别以自身中心等比缩放两个眼球，先测试 `0.94 - 1.06`，
   不要同时围绕世界原点缩放，否则眼距也会改变。
4. 在 `Body` 上创建 `Face_EyeSocketSize_Pos`。
5. 进入 Edit Mode，只选择 `REGION_EyeSocket_L/R`；再次确认耳朵、头皮、
   眉毛主体和眼球没有被选中。
6. 分别以每只眼睛中心为枢轴，调整上下眼皮和内外眼角形成的包围圈。不能
   把左右眼一起围绕头部中心缩放。
7. 显示眼球对象，检查正面、侧面和四分之三视角，眼皮必须包住眼球。
8. 在极值处仍露眼或穿眼时，记录并制作
   `Corrective_LargeEye_Eyelid`，不能扩大整块额头来遮盖。
9. 从 `Basis` 单独制作 `Face_EyeSocketSize_Neg`，检查眼皮不能切进眼球。
10. 最后单独测试眼距、眼睛高低和眼角倾斜，确认四个含义没有被混在一个
    Shape Key 中。

如果步骤 5 无法得到干净的左右眼眶区域，应停止眼睛大小制作并返回第 4 节
修正语义区域。继续用空间圆球扩大选区只会再次误伤耳朵和头皮。

## 9. 第二阶段 Shape Key

第一阶段全部通过后，再按实际辨识度逐项增加：

```text
Body_HipDepth_Pos / Body_HipDepth_Neg

Face_ForeheadWidth_Pos / Face_ForeheadWidth_Neg
Face_CheekboneWidth_Pos / Face_CheekboneWidth_Neg
Face_LowerFullness_Pos / Face_LowerFullness_Neg
Face_MuzzleHeight_Pos / Face_MuzzleHeight_Neg
Face_UpperLidOpen_Pos / Face_UpperLidOpen_Neg
Face_NoseHeight_Pos / Face_NoseHeight_Neg
Face_MouthHeight_Pos / Face_MouthHeight_Neg
Face_MouthCurve_Pos / Face_MouthCurve_Neg
Face_BrowHeight_Pos / Face_BrowHeight_Neg
Face_BrowAngle_Pos / Face_BrowAngle_Neg
```

`MouthCurve` 只表示中性嘴角轮廓，不能把开心或难过表情烘焙进身份外貌。

## 10. 耳朵、尾巴和毛发

### 10.1 耳朵

有耳骨时优先使用耳骨：

- 耳朵大小：左右耳骨统一缩放。
- 耳朵倾斜：左右耳骨旋转。
- 轻微不对称：左右耳使用受限的不同数值。
- 折耳：耳骨姿态加 `Corrective_DroopEar_EarRoot`。

没有耳骨时，创建：

```text
Ear_Size_Pos / Ear_Size_Neg
Ear_Width_Pos / Ear_Width_Neg
Ear_Tilt_Pos / Ear_Tilt_Neg
```

只使用 `REGION_Ear_L/R`，耳根 `LOCK_EarRoot_L/R` 保持稳定。

### 10.2 尾巴

尾巴长度使用 `Tail_01...Tail_04` 骨链长度，尾巴粗细使用：

```text
Tail_Thickness_Pos / Tail_Thickness_Neg
```

尾巴蓬松轮廓仅在网格确实有足够毛发几何时创建 `Fur_TailFluff`。尾尖颜色
使用材质遮罩，不使用 Shape Key。

### 10.3 毛发轮廓

以下项目都是可选项，没有独立毛片或足够拓扑时不要创建空参数：

```text
Fur_BodyLength
Fur_HeadTuft
Fur_CheekRuff
Fur_ChestRuff
Fur_EarTuft
Fur_LimbFeathering
Fur_TailFluff
```

## 11. 必需的组合修正

主 Shape Key 完成后检查以下组合。发现穿模或接缝塌陷时才创建修正项：

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

修正项不是用户可见参数，也不随机采样。运行时根据相关参数组合自动计算
权重。组合修正涉及从混合形态中隔离增量，操作错误会重复叠加主形变；第一
阶段先记录问题组合，由技术美术或后续专用工具制作，不要直接复制混合结果
当作普通 Shape Key。

## 12. 制作毛色遮罩

第一版使用两张 RGBA 贴图，每个通道保存一个灰度区域：

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

操作流程：

1. 确认身体 UV 没有重叠到不相关部位。
2. 在 UV Editor 新建与主贴图相同分辨率的 RGBA 图片。
3. 在 Edit Mode 通过 `COAT_` 区域组选择对应面。
4. 在 Texture Paint 中为目标通道填白，其他区域保持黑色。
5. 边界使用短距离灰度过渡，不能出现大面积模糊串色。
6. 单独查看每个通道，确认没有把眼球、牙齿和鼻子错误涂进毛色区域。
7. 保存 PNG，不能只把图片留在未保存的 Blender 内存中。

主色变化必须被毛发区域限制，不能连眼球、鼻子和牙齿一起变色。

## 13. 极值和组合验收

每个 Shape Key 都按以下流程验收：

1. 所有参数设为 `0`，保存中性视图。
2. 目标 `Pos` 设为 `1`，检查正面、侧面和四分之三视角。
3. 恢复 `0`，目标 `Neg` 设为 `1`，重复检查。
4. 在 `0` 和 `1` 间快速切换，确认只有目标区域变化。
5. 播放 `idle`、`walking`、`running` 和一个大幅手臂动作。
6. 检查眼球、眼皮、嘴角、腋下、胯部、膝盖和尾根。

至少保存以下组合预设用于对比：

```text
Extreme_TallLean
Extreme_ShortRound
Extreme_LargeHeadSmallBody
Extreme_SmallHeadLongLeg
Extreme_WideFaceLargeEye
Extreme_NarrowFaceLongMuzzle
```

每张对比图必须使用同一相机、同一焦距、同一地面线和同一角色位置。禁止
让相机自动适配每个角色，否则最高和最矮看起来仍然一样高。

### 13.1 拒绝条件

- 眼睛参数移动了耳朵、头皮或另一只眼睛。
- 肚子参数移动了手臂、背部、腿根或尾巴。
- 四肢粗细在关节处形成明显台阶。
- 窄脸后眼球露出脸外。
- 胖脸后嘴角陷入脸颊。
- 大头后颈部断裂或穿入下颌。
- 动画播放时 Shape Key 消失、抖动或导致关节撕裂。
- 参数设为 `1` 后肉眼仍无法从正确观察角度分辨。

## 14. 导出 GLB

1. 所有身份 Shape Key 值恢复为 `0`。
2. 清除测试 Pose、Action 和 NLA Strip。
3. 只选择角色网格、独立眼球、其他必要部件和 Armature。
4. 执行 `File -> Export -> glTF 2.0`。
5. 选择 Binary `.glb`。
6. 启用 Skinning、Shape Keys/Morph Targets 和材质。
7. 不导出相机、灯光、控制笼和测试物体。
8. 导出后在空 Blender 文件中重新导入 GLB。
9. 确认骨骼名称、贴图和所有 Shape Key 名称完整。
10. 在 Godot 中确认 `MeshInstance3D` 能按名称找到所有 blend shape。

## 15. 每个物种的制作顺序

不要同时在狗和狐狸上试错。先完整做通一个狐狸母版，再把相同语义迁移到
狗，但狗必须重新选择区域并重新雕刻，不能复制狐狸的顶点数据。

### 阶段 A：结构准备

- [ ] 使用原始绑骨 `.blend` 保存母版副本。
- [ ] 整理对象并确认眼球、牙齿、舌头和毛发结构。
- [ ] 建立全部第一阶段 `REGION_` 顶点组。
- [ ] 建立必要的 `LOCK_` 保护组。
- [ ] 修正每个区域边缘权重并通过选择检查。

### 阶段 B：骨骼比例

- [ ] 校准整体身高、头、颈、手臂、腿、肩和手脚范围。
- [ ] 使用公共动画测试所有最小值和最大值。
- [ ] 记录每个范围，不改公共骨名称和参考姿态。

### 阶段 C：第一阶段 Shape Key

- [ ] 完成 8 组身体形态。
- [ ] 完成 12 组高辨识度脸部形态。
- [ ] 分离眼球或明确禁用眼球缩放。
- [ ] 完成耳朵和尾巴必要控制。
- [ ] 所有正负极值均通过三视图检查。

### 阶段 D：颜色和组合修正

- [ ] 完成两张 RGBA 毛色遮罩。
- [ ] 提供物种合法色板和花纹。
- [ ] 检查极端组合并记录需要的 Corrective。
- [ ] 完成正式 GLB 导出和重新导入验收。

## 16. 物种母版记录表

每个物种复制一份以下记录，未完成的参数必须写 `disabled`，不能只在配置中
声明一个实际上没有效果的字段。

```text
species: fox
source_blend: fox_appearance_master_v001.blend
profile_version: 1

objects:
  body: Body
  armature: Armature
  eye_left: Eye_L | embedded | missing
  eye_right: Eye_R | embedded | missing
  teeth: Teeth | embedded | missing
  tongue: Tongue | embedded | missing

bone_ranges:
  stature: min=?, base=1.0, max=?
  head_scale: min=?, base=1.0, max=?
  neck_length: min=?, base=1.0, max=?
  arm_length: min=?, base=1.0, max=?
  leg_length: min=?, base=1.0, max=?
  shoulder_width: min=?, base=1.0, max=?
  hand_scale: min=?, base=1.0, max=?
  foot_scale: min=?, base=1.0, max=?

regions:
  REGION_Chest: ready | needs_fix | missing
  REGION_Belly: ready | needs_fix | missing
  REGION_Skull: ready | needs_fix | missing
  REGION_EyeSocket_L: ready | needs_fix | missing
  REGION_EyeSocket_R: ready | needs_fix | missing
  ...

shape_keys:
  Body_BellyDepth_Pos: ready | needs_fix | disabled
  Body_BellyDepth_Neg: ready | needs_fix | disabled
  Face_SkullWidth_Pos: ready | needs_fix | disabled
  Face_SkullWidth_Neg: ready | needs_fix | disabled
  ...

coat_masks:
  coat_regions_0.png: ready | needs_fix | missing
  coat_regions_1.png: ready | needs_fix | missing

known_correctives:
  Corrective_LargeEye_Eyelid: ready | needed | not_needed
  Corrective_NarrowFace_EyeContainment: ready | needed | not_needed
  ...
```

## 17. 最小可交付标准

第一版不以“参数数量多”为完成标准，而以实际可辨识和可运行为标准：

- 至少 6 个通过验收的骨骼比例参数。
- 至少 8 组身体 Shape Key。
- 至少 10 组脸部 Shape Key。
- 至少 2 个耳朵控制和 1 个尾巴粗细控制。
- 至少 2 张毛色区域遮罩、4 个色板和 3 个花纹。
- `Extreme_TallLean` 与 `Extreme_ShortRound` 全身差异明显。
- `Extreme_WideFaceLargeEye` 与 `Extreme_NarrowFaceLongMuzzle` 头像差异明显。
- 所有极值都能播放公共待机、行走和跑步动画。
- GLB 与 Godot 均能找到全部正式启用的 morph target。

任何误动非目标区域的 Shape Key 都应标记为 `needs_fix`，不能因为列表中已经
存在这个名字就计入完成数量。
