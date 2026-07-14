@tool
extends Node3D

## 从修改后的房间场景提取家具到家具集合
## 使用方法：在 Godot 编辑器中打开此场景，点击 "Extract All" 按钮

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

@export var extract_all: bool = false:
	set(value):
		if value:
			_extract_all_rooms()

@export var room_index: int = 0
@export var extract_single: bool = false:
	set(value):
		if value and room_index >= 0 and room_index < SOURCE_ROOMS.size():
			_extract_room(room_index)


func _extract_all_rooms() -> void:
	print("=== 开始提取所有房间的家具 ===")
	for i in range(SOURCE_ROOMS.size()):
		_extract_room(i)
	print("=== 提取完成 ===")


func _extract_room(index: int) -> void:
	var source_path := SOURCE_ROOMS[index]
	var target_path := TARGET_SETS[index]
	
	print("提取房间 %d: %s -> %s" % [index + 1, source_path, target_path])
	
	# 加载源房间
	var source_scene := load(source_path) as PackedScene
	if not source_scene:
		push_error("无法加载源房间: %s" % source_path)
		return
	
	var source_room := source_scene.instantiate() as Node3D
	
	# 查找家具节点（排除墙壁、地板、地板等建筑元素）
	var furniture := Node3D.new()
	furniture.name = "Furniture"
	
	# 遍历所有子节点，提取非建筑元素
	for child in source_room.get_children():
		var child_name := child.name.to_lower()
		
		# 跳过明显的建筑元素
		if child_name.contains("wall") or child_name.contains("floor") or \
		   child_name.contains("ceiling") or child_name.contains("roof") or \
		   child_name.contains("reference"):
			print("  跳过建筑元素: %s" % child.name)
			continue
		
		# 保留家具
		print("  保留家具: %s" % child.name)
		source_room.remove_child(child)
		furniture.add_child(child)
		child.owner = furniture
	
	# 创建新的家具集合场景
	var furniture_set := Node3D.new()
	furniture_set.name = TARGET_SETS[index].get_file().get_basename()
	
	# 添加参考墙（从参考框场景）
	var reference_frame := _create_reference_frame()
	furniture_set.add_child(reference_frame)
	
	# 添加家具
	furniture_set.add_child(furniture)
	furniture.owner = furniture_set
	
	# 保存场景
	var scene := PackedScene.new()
	var result := scene.pack(furniture_set)
	if result == OK:
		var err := ResourceSaver.save(scene, target_path)
		if err == OK:
			print("✓ 保存成功: %s" % target_path)
		else:
			push_error("保存失败: %s (错误码: %d)" % [target_path, err])
	else:
		push_error("打包失败: %s" % target_path)
	
	source_room.queue_free()


func _create_reference_frame() -> Node3D:
	"""创建参考墙"""
	var ref_walls := Node3D.new()
	ref_walls.name = "ReferenceWalls"
	
	# 后墙（青色）
	var back_wall := MeshInstance3D.new()
	back_wall.name = "BackWall"
	back_wall.mesh = BoxMesh.new()
	back_wall.mesh.size = Vector3(0.1, 3.0, 5.6)
	back_wall.position = Vector3(-1.85, 1.5, 0)
	var back_mat := StandardMaterial3D.new()
	back_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	back_mat.albedo_color = Color(0, 0.8, 1, 0.3)
	back_wall.surface_material_override/0 = back_mat
	ref_walls.add_child(back_wall)
	
	# 左墙（橙色）
	var left_wall := MeshInstance3D.new()
	left_wall.name = "LeftWall"
	left_wall.mesh = BoxMesh.new()
	left_wall.mesh.size = Vector3(3.7, 3.0, 0.1)
	left_wall.position = Vector3(0, 1.5, 2.8)
	var left_mat := StandardMaterial3D.new()
	left_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	left_mat.albedo_color = Color(1, 0.5, 0, 0.3)
	left_wall.surface_material_override/0 = left_mat
	ref_walls.add_child(left_wall)
	
	# 右墙（绿色）
	var right_wall := MeshInstance3D.new()
	right_wall.name = "RightWall"
	right_wall.mesh = BoxMesh.new()
	right_wall.mesh.size = Vector3(3.7, 3.0, 0.1)
	right_wall.position = Vector3(0, 1.5, -2.8)
	var right_mat := StandardMaterial3D.new()
	right_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	right_mat.albedo_color = Color(0, 1, 0.5, 0.3)
	right_wall.surface_material_override/0 = right_mat
	ref_walls.add_child(right_wall)
	
	return ref_walls