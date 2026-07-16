# 角色资源

`characters/` 与 `rooms/` 是并列模块。每个角色资产使用独立子目录，保存
模型、动画、贴图和可实例化场景，不放入 `rooms/assets/`。

## 当前角色包

`characters/elfie/` 是第一套可运行的精灵角色资产包：

- `character.fbx`：共享的角色模型和骨骼
- `character_*.png`：模型贴图
- `animation/`：待机、行走、跑步、转身、跳跃等动画
- `elfie_3d.tscn`：带 `CharacterBody3D` 和胶囊碰撞体的实例场景

场景当前引用的 14 个模型和动画资源必须一起保留；运行时创建多只精灵时
复用这套资源，不复制 FBX 文件。

## 目录边界

- 角色资产：`godot/characters/<asset_id>/`
- Godot 通用运行时脚本：`godot/runtime/`（后续建立）
- 精灵个体身份、性格和记忆：由 Python 的 `elfie_id` 和本地数据目录管理
- 房间、家具和摄像头：`godot/rooms/`

以后增加猫、狐狸或其他物种时，新增 `characters/<asset_id>/`，不把个体
配置复制进角色资产目录。当前先保留 `elfie/` 名称，待运行时接入验证后再
决定是否按物种改名，避免在资源未验收前产生无意义的路径迁移。
