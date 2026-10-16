# 园区视觉资产基线

> [English](README.md)

在仓库要求的 Godot 4.7 工程中打开 `res://rooms/estate/estate.tscn`。
场景包含一栋主楼和八个可独立寻址的小屋实例（`M01`–`M08`），小屋共享同一份
`pod.glb`。该场景未接入 `main.tscn` 或现有 Runtime。

| 资源 | 内容 | 大小 |
| --- | --- | --- |
| `central.glb` | 当前主楼一至三层家具试版，保留原第四层及建筑 | 69,420,928 字节 |
| `pod.glb` | 已确认的小屋完整定稿 02，包含四套家具 | 39,715,472 字节 |

主楼是开发快照，尚未作为美术最终版确认。小屋建筑和一楼家具与已确认来源一致；
原有露台道具随模型保留，不代表露台布置另行获得确认。本包不含碰撞、导航、交互逻辑
或水流动画，也不含室外花园、Blender 源文件、效果图、历史版本、无引用场景数据和导入缓存。

两份 GLB 均内嵌贴图，加载已提交场景不需要 `build/asset_previews/` 中的任何文件。
`manifest.json` 记录来源版本、SHA-256 和数据保留检查。此次导出没有减面，也没有
合并独立家具部件，原功能和楼层标签均保留。

坐标单位为米，采用 glTF 右手系、Y 轴向上。主楼保留原世界坐标。
小屋 GLB 通过来源锚点的逆矩阵包装，形成可复用的局部坐标。
`placements.json` 以列主序保存八个原始锚点矩阵，`estate.tscn` 直接应用这些矩阵；
不要对 GLB 再重复平移或旋转。小屋子节点保留来源模块标签 `M01`，区分八栋独立小屋
时使用各场景实例的 `metadata/module`（`M01`–`M08`）。

通过仓库受控入口运行聚焦资源检查：

```sh
bash scripts/quality/checks/godot_host.sh res://scripts/test/test_estate_asset_baseline.gd
```
