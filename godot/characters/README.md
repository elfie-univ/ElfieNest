# 角色资源

`characters/` 与 `rooms/` 是并列模块。每个角色使用独立子目录，保存该角色的场景、模型、动画和专属纹理，不放入 `rooms/assets/`。

当前 `elfie/elfie_3d.tscn` 仍需要以下原始资源才能完整加载：

- `elfie/character.fbx`
- `elfie/animation/` 下场景引用的 13 个动画 FBX

这些文件在目录重构前就未包含在仓库中。本轮只统一了引用路径；根 `main.tscn` 暂不实例化角色，因此缺失文件不影响房间主场景运行。
