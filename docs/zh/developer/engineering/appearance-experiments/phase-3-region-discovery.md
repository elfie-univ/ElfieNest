# 外观实验——第三阶段：正式语义区域

**状态：** 13个正式区域已经冻结并接入运行时。

**日期：** 2026-08-17 开始发现；2026-08-19 接受正式基线。

## 范围与结论

本阶段在不修改狗、狐狸 GLB 的前提下确定了可复用局部区域。最终结果不再保留独立实验 Shader：

- `godot_project/runtime/actor/actor_appearance.gd` 是正式区域公式和 V9 相对明暗组合的唯一来源；
- `godot_project/scripts/test/render_production_region_debug.gd` 是唯一可重放的区域基线渲染器，
  区域分类直接委托给 `ActorAppearance`；
- 狗和狐狸共用同一套13区协议，但允许物种专属几何阈值；
- 每个候选最多启用两个可染色区域。

此前27轮发现过程在调边界时有价值，但正式提升后已经清除，避免它们继续成为第二事实源。其长期
结果只保留为正式公式、本决策记录和下面的紧凑正式基线。

## 重放方法

从仓库根目录执行，要求 Godot 4.7 且没有其他 Godot 实例：

```text
APPEARANCE_FORMAL_REGION_OUTPUT=/private/tmp/elfienest-formal-regions \
/Applications/Godot.app/Contents/MacOS/Godot --display-driver macos \
  --rendering-method gl_compatibility --path godot_project \
  --script res://scripts/test/render_production_region_debug.gd
```

渲染器会在临时目录写出狗、狐狸总图、逐区图片、逐视角图片和机器可读目录。仓库只保留两张紧凑
总图和目录作为发布证据。

## 冻结基线

[正式区域基线清单](../../../../public/assets/appearance-experiments/phase-3/production-region-baseline-v1.json)

![狗正式区域总图](../../../../public/assets/appearance-experiments/phase-3/production-v1/dog-formal-region-grid-4views.png)

![狐狸正式区域总图](../../../../public/assets/appearance-experiments/phase-3/production-v1/fox-formal-region-grid-4views.png)

每行对应一个区域，四列依次为正面、四分之三、侧面和俯视。高亮颜色只用于定位；产品局部染色
仍使用与基础毛色相同的 V9 局部相对明暗迁移。

## 区域契约

| ID | Key | 允许操作 |
| ---: | --- | --- |
| 0 | `head_tuft` | 染色 |
| 1 | `forehead_mark_zone` | 仅额头符号 |
| 2 | `ear_pair` | 染色 |
| 3 | `ear_tip_pair` | 染色 |
| 4 | `cheek_fluff` | 仅腮红、雀斑或痣 |
| 5 | `chest_tuft` | 染色或爱心 |
| 6 | `belly_center` | 仅爱心 |
| 7 | `forearm_paw_pair` | 染色 |
| 8 | `elbow_cuff_pair` | 肘后圆斑染色 |
| 9 | `lower_leg_foot_pair` | 染色 |
| 10 | `knee_cuff_pair` | 膝前圆斑染色 |
| 11 | `tail_tip` | 染色 |
| 12 | `tail_underside` | 染色 |

可染色 ID 为 `0、2、3、5、7、8、9、10、11、12`。除明确允许的安全标记外，额头、眼睛、
眉毛、鼻子、嘴、牙齿和爪子继续受保护。

## 冻结边界

正式实现使用计算后的3D模型坐标和原始材质贴图采样，不是屏幕空间遮罩，也不在截图上后处理。
修改区域必须重新提供狗和狐狸的多视角基线，且不得新增第二套换色或区域分类器。暂缓的跨身体
外星纹样不属于本契约。
