# Godot 项目目录规则

本文件只作用于 `godot_project/`。

- 打开、运行、调试、截图或关闭 Godot 前，必须先读取并执行
  `../.agents/skills/godot-project-operator/SKILL.md`。
- 按该技能检查现有进程和 `project.godot` 声明的版本；未经用户同意不得用不匹配
  版本编辑项目，不得创建重复实例。
- 操作前后检查 Git 状态，不保留 `.godot/`、导入缓存或编辑器自动产生的无关改动。
- Godot 相关事实以 `project.godot`、源码资源以及直接相关的 `test/godot/` 或
  architecture 测试为准，不以旧设计文档替代当前实现。
