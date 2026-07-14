#!/usr/bin/env godot --headless --script
extends SceneTree

## Headless 家具提取脚本
## 从修改后的房间场景提取家具到家具集合

const SOURCE_ROOMS := [
	"res://modular_rooms/common_area/1_kitchen_room.tscn",
	"res://modular_rooms/common_area/2_sitting_room.tscn",
	"res://modular_rooms/common_area/3_media_room.tscn",
	"res://modular_rooms/common_area/4_gym.tscn",
	"res://modular_rooms/common_area/5_garden.tscn",
	"res://modular_rooms/common_area/6_working_room.tscn",
	"res://modular_rooms/common_area/7_music_room.tscn",
	"res://modular_rooms/common_area/8_bookroom.tscn",
]

const TARGET_SETS := [
	"res://modular_rooms/assets/furniture_sets/kitchen_furniture_set.tscn",
	"res://modular_rooms/assets/furniture_sets/sitting_furniture_set.tscn",
	"res://modular_rooms/assets/furniture_sets/media_furniture_set.tscn",
	"res://modular_rooms/assets/furniture_sets/gym_furniture_set.tscn",
	"res://modular_rooms/assets/furniture_sets/garden_furniture_set.tscn",
	"res://modular_rooms/assets/furniture_sets/working_furniture_set.tscn",
	"res://modular_rooms/assets/furniture_sets/music_furniture_set.tscn",
	"res://modular_rooms/assets/furniture_sets/bookroom_furniture_set.tscn",
]


func _init():
	print("=== 开始提取家具 ===")
	
	for i in range(SOURCE_ROOMS.size()):
		extract_room(i)
	
	print("=== 提取完成 ===")
	quit()


func extract_room(index: int) -> void:
	var source_path: String = SOURCE_ROOMS[index]
	var target_path: String = TARGET_SETS[index]
	
	print("\n房间 %d: %s" % [index + 1, source_path.get_file()])
	
	# 加载源房间
	var source_scene := load(source_path) as PackedScene
	if not source_scene:
		push_error("  ✗ 无法加载源房间")
		return
	
	var source_room := source_scene.instantiate() as Node3D
	
	# 统计家具
	var furniture_count := 0
	for child in source_room.get_children():
		var child_name := child.name.to_lower()
		if not (child_name.contains("wall") or child_name.contains("floor") or \
				child_name.contains("ceiling") or child_name.contains("reference")):
			furniture_count += 1
	
	print("  找到 %d 个家具节点" % furniture_count)
	
	# 直接复制整个房间场景到家具集合
	# 这样保留了所有家具的相对位置
	var scene := PackedScene.new()
	var result := scene.pack(source_room)
	
	if result == OK:
		var err := ResourceSaver.save(scene, target_path)
		if err == OK:
			print("  ✓ 保存成功: %s" % target_path.get_file())
		else:
			push_error("  ✗ 保存失败 (错误码: %d)" % err)
	else:
		push_error("  ✗ 打包失败")
	
	source_room.queue_free()