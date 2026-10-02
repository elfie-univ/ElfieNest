# Myelle 制作源文件

> English：[README.md](README.md)

- `myelle-concept-reference.png`：用户提供的橙色角色参考图。
- `myelle-tail-corrected.blend`：兼容 Mixamo 的模型，包含 `Tail_01` 至
  `Tail_04`、归一化尾部权重和嵌入式源贴图。
- 输入：用户提供的 `base_basic_shaded (2).fbx`，接收日期为 2026-10-02。
- 制作工具：Blender 5.2.0 LTS。运行时模型：`../myelle.glb`。

GLB 已应用骨架对象旋转，不导出动作；原 shaded 贴图作为 PBR 主色而非自发光。
运行时动作统一来自 `characters/animation/`。原始 FBX 保持不变。

图片/3D 生成服务、模型版本、生成日期与再分发许可证未提供，分发前需要确认。
本制作源目录不参与 Godot 导入和发布导出。
