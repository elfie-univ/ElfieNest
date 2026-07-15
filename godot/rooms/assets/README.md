# 房间组件资产

`rooms/assets/` 只保存用于拼装房间的组件和视觉资源，不保存角色，也不保存完整房间布局。

- `beds/`：床和床边组件，使用 `.tscn`。
- `chairs/`、`tables/`、`storage/`：椅子、桌子、书架等家具组件，使用 `.tscn`。
- `exercise/`、`instruments/`、`teleporter/`：功能型房间组件；模型使用 `.glb`，Godot 组合使用 `.tscn`。
- `materials/`：可复用材质和纹理，材质使用 `.tres`，纹理优先使用 `.png` 或 `.webp`。
- `themes/`：房间配色和主题配置。
- `artwork/gallery/`：可用于壁纸、壁画和相框的图片库；照片使用 `.jpg`，需要透明通道的图使用 `.png` 或 `.webp`。
- `reference/`：仅供制作和对齐组件时参考，不参与运行时房间拼装。

图片和模型旁的 `.import` 文件由 Godot 管理。移动源文件时需要一起移动并重新导入，不手工维护 `.godot/imported/` 下的缓存文件。
