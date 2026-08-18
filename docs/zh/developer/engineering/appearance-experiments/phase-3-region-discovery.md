# 外观实验——第三阶段：3D 区域识别

**状态：** 已实现 Godot 区域发现/调试预览；区域边界还没有作为生产成品批准。

**日期：** 2026-08-17

## 本阶段范围

本阶段只验证一个问题：在分配颜色、生成组合之前，能不能在现有狗和狐狸 GLB 网格上找到可复用的
局部区域？

结论是：**核心区域可以找到**，但狗和狐狸需要物种专属的区域规则。本实验不修改 GLB、场景几何、
BlendShape、脸型、生产着色器行为或领养服务。

## 实现方法

`godot_project/scripts/test/render_appearance_region_debug.gd` 使用真实 Godot OpenGL/Metal 渲染器，
从正面、四分之三、侧面和俯视四个角度渲染原始场景。俯视图专门检查头顶毛的前后覆盖和尾根串色。
调试 shader 读取
`MODEL_MATRIX * VERTEX` 得到实际可见的模型坐标，把 GLB 导入时的骨骼厘米坐标换算成场景中的米制坐标，
再按候选区域着色，也可以单独隔离某一个区域。

这样验证的是 3D 区域是否跟着模型走，不是旧的“跟着领养卡片镜头画椭圆”的屏幕空间遮罩。它仍然是
区域发现工具，不代表这些阈值已经是最终美术遮罩。

从仓库根目录使用桌面渲染器重放：

```text
APPEARANCE_REGION_OUTPUT=/private/tmp/elfienest-appearance-reference/phase-3 \
/Applications/Godot.app/Contents/MacOS/Godot --display-driver macos \
  --rendering-method gl_compatibility --path godot_project \
  --script res://scripts/test/render_appearance_region_debug.gd
```

调试开关：

- `APPEARANCE_REGION_SELECTED=0..12`：只显示某个区域的四视角结果；
- `APPEARANCE_REGION_HEATMAP=1`：显示实际局部坐标热力图，而不是区域颜色；
- `APPEARANCE_REGION_COLOR_PREVIEW=1`：保留原始材质，只在候选区域上叠加半透明测试色，用真实毛发检查边界和空洞。

脚本同时写出 `region-catalog.json`：记录每个实际分色区域的编号、颜色、目标说明和排除说明，供视觉模型评测这张实际渲染图；它不是预先提供的答案遮罩。

## 已保存基线与特殊符号目录

下一步实验统一从 round 27 开始。现在把它保存成显式基线，避免后续改区域时悄悄覆盖已经复核过的证据：

[区域基线清单](../../../public/assets/appearance-experiments/phase-3/region-baseline-v1.json)

round-27 的总图、13 个区域各自的四视角图，是当前实验区域定义的唯一参考。它仍然不是生产批准，
只是冻结下一轮视觉实验必须从哪一版开始。

特殊标记单独保存，不混进区域基线。视觉目录包含 15 个候选形状，JSON 同时记录推荐位置，并把
“脸颊晕染”和“尾环”明确为部位专用标记，而不是额头符号：

[特殊符号候选目录](../../../public/assets/appearance-experiments/phase-3/special-symbol-catalog.svg)

[特殊符号目录数据](../../../public/assets/appearance-experiments/phase-3/special-symbol-catalog.json)

## 区域决策表

| 区域 key | 狗 | 狐狸 | 当前结论 |
| --- | --- | --- | --- |
| `head_tuft` | 头顶中央向上突出的单撮毛 | 头顶中央向上突出的单撮毛 | 核心候选；只取中间小撮，不取整个头顶。 |
| `forehead_mark_zone` | 发际线到眉毛之间的中央区域 | 同一语义区域 | 核心安全区候选；眼睛、鼻子、嘴保持保护。 |
| `ear_pair` | 整片垂耳 | 可见的耳内/前侧区域 | 核心候选，但按物种定义；“耳内”不能强行作为两物种同一含义。 |
| `ear_tip_pair` | 下垂耳瓣最下端 | 立耳最上端/最外端 | 核心候选；需要和耳朵大区域一起复核，保证不重叠。 |
| `cheek_fluff` | 外侧脸颊/嘴边毛 | 脸颊绒毛/嘴套毛 | 核心候选；中央眼睛、鼻子、嘴不纳入。 |
| `chest_tuft` | 上胸口的心形胸毛 | 上胸口的心形胸毛，针对狐狸向下偏移 | 核心候选；长条白腹继续由腹部区域独立控制。 |
| `belly_center` | 腹部中心毛 | 腹部中心毛 | 核心候选；作为一块自然区域，不做成小肚脐点。 |
| `forearm_paw_pair` | 前臂和手 | 前臂和手 | 核心候选；默认左右共用一个槽位。 |
| `lower_leg_foot_pair` | 小腿和脚 | 小腿和脚 | 核心候选；已降低上边界，避免包含手指尖。 |
| `tail_tip` | 侧面可见的尾尖小区域 | 侧面清晰的尾尖 | 核心候选，狐狸更稳定；正面可能被身体遮挡。 |
| `tail_underside` | 探索中 | 探索中 | 仍需按物种验证尾巴下侧，暂不进入组合。 |
| `elbow_cuff_pair` / `knee_cuff_pair` | 当前单网格坐标会和邻近肢体重叠 | 同样 | 仅实验区域；不进入第一批颜色组合。 |

### 保护区域

眼睛、眉毛、鼻子、嘴、牙齿、爪子等深色身份细节不是可选外观区域，继续使用原始渲染细节。
保护边界通过语义区域约束实现，不再靠屏幕空间手工画大圆圈。

## 视觉证据

![狗区域调试图](../../../public/assets/appearance-experiments/phase-3/dog-region-debug.png)

![狐狸区域调试图](../../../public/assets/appearance-experiments/phase-3/fox-region-debug.png)

每张图分两行：上面是原始渲染，下面是区域颜色图；四列依次是正面、四分之三、侧面和俯视。脚本同时
打印并写出区域稳定的数字 ID、key、中文标签、颜色、目标说明和排除说明。逐区复核时先看解剖位置，再看
范围是否扩大、缩小、漏区或串区，并参考上面的原始渲染；不能因为颜色显眼就把错误位置判为通过。

产品视角的真实叠色验证：

![狗区域配色预览](../../../public/assets/appearance-experiments/phase-3/dog-region-color-preview.png)

![狐狸区域配色预览](../../../public/assets/appearance-experiments/phase-3/fox-region-color-preview.png)

单独验证两个修正后的区域：

![狗头顶中央小撮](../../../public/assets/appearance-experiments/phase-3/dog-region-color-preview-selected-00-head_tuft.png)

![狗心形胸毛](../../../public/assets/appearance-experiments/phase-3/dog-region-color-preview-selected-05-chest_tuft.png)

![狐狸头顶中央小撮](../../../public/assets/appearance-experiments/phase-3/fox-region-color-preview-selected-00-head_tuft.png)

![狐狸心形胸毛](../../../public/assets/appearance-experiments/phase-3/fox-region-color-preview-selected-05-chest_tuft.png)

### 产品角度复核结论

- 头顶小撮必须同时通过四个视角；俯视图用于检查前后是否漏掉一半，周围额头保持原样。
- 胸毛现在读起来是上胸心形区域，腹部仍然是独立区域；狐狸因为导入网格的颈胸交界更低，单独向下偏移了一点。
- 之前看到的黑色空洞，主要是预览替换了源材质，以及法线朝向筛选过严造成的。现在改为在原始材质上叠色，并放宽毛束方向限制；剩下的细小明暗是原始毛发纹理，不是大片空白洞。
- 全量叠色图只是检查边界，不是最终配色。多个互不协调的测试色同时使用会显得杂乱，后面搭配颜色时要按物种使用少量自然色系。

## 边界与下一步规则

1. 四视角区域边界确认之前，不进入颜色搭配。
2. 狗和狐狸继续使用同一套区域协议，但允许物种专属几何规则。
3. 左右成对区域默认共用一个颜色槽；不对称是后续的受控选项。
4. 区域后续应作为已接受的相对明暗迁移的语义输入，不能拍平原始毛发明暗，也不能叠加一层宽泛
   的半透明雾状遮罩。
5. 复核通过后，只把已接受的区域定义提升到生产外观契约，再验证颜色组合、过渡宽度、禁区保护和
   确定性候选 key。

## 当前上限

现在的狗、狐狸 GLB 各自都是单个主体网格，没有现成的耳朵、胸口、尾巴材质 ID。单纯用局部坐标可以
稳定找到大块解剖区域，但不一定能区分同一只耳朵的内外表面，也不一定能区分肘部环和附近的手；这
些歧义会直接显示在调试图里，并保持为“未批准”，不会被默认为成品遮罩。
