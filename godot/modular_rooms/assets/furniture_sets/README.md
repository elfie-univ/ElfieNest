# 家具组合预制件提取指南

## 什么是"家具组合预制件"？

每个活动区的家具组合，已经调整好相对位置，可以直接使用。

例如：`kitchen_furniture_set.tscn`
```
Node3D (根节点)
├── Counter (厨台) - position: (1.2, 0, 0)
├── Refrigerator (冰箱) - position: (-2.5, 0, 1.3)
├── Shelves (架子) - position: (0, 0, -2.1)
└── Dinner_Table (餐桌) - position: (0, 0, 3.5)
```

## 如何创建？

### 方法 1：从现有房间提取（推荐）

1. 在 Godot 编辑器中打开 `room/common_area/1_kitchen_room.tscn`
2. 创建新的 Node3D 作为根节点
3. 将所有家具节点拖到新的根节点下
4. 删除墙壁、地板、地毯等建筑元素
5. 保存为 `modular_rooms/assets/furniture_sets/kitchen_furniture_set.tscn`

### 方法 2：手动摆放（如果需要重新设计）

1. 创建新的场景文件
2. 实例化家具预制件（从 room/assets/）
3. 手动拖拽调整位置
4. 保存

## 文件命名

- `kitchen_furniture_set.tscn` - 厨房家具组合
- `sitting_furniture_set.tscn` - 客厅家具组合
- `media_furniture_set.tscn` - 影音室家具组合
- `gym_furniture_set.tscn` - 健身房家具组合
- `garden_furniture_set.tscn` - 花园家具组合
- `working_furniture_set.tscn` - 工作室家具组合
- `music_furniture_set.tscn` - 音乐室家具组合
- `bookroom_furniture_set.tscn` - 书房家具组合

## 更新 activity_room.gd

修改后：
```gdscript
const FURNITURE_SETS := [
	preload("res://modular_rooms/assets/furniture_sets/kitchen_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/sitting_furniture_set.tscn"),
	# ...
]

func _build_furniture(kind: int) -> void:
	var furniture_set := FURNITURE_SETS[kind].instantiate()
	_generated.add_child(furniture_set)
	# 不需要隐藏墙壁了！
```
