@tool
class_name ModularNestFinal
extends Node3D

## 最终完整宿舍 - 使用修改后的8个房间场景
## 标准布局：走廊两侧排列房间

const D := preload("res://modular_rooms/room_dimensions.gd")
const G := preload("res://modular_rooms/modular_geometry.gd")

const ROOM_SCENES := [
	preload("res://modular_rooms/common_area/1_kitchen_room.tscn"),
	preload("res://modular_rooms/common_area/2_sitting_room.tscn"),
	preload("res://modular_rooms/common_area/3_media_room.tscn"),
	preload("res://modular_rooms/common_area/4_gym.tscn"),
	preload("res://modular_rooms/common_area/5_garden.tscn"),
	preload("res://modular_rooms/common_area/6_working_room.tscn"),
	preload("res://modular_rooms/common_area/7_music_room.tscn"),
	preload("res://modular_rooms/common_area/8_bookroom.tscn"),
]

@export var generate_dorm: bool = true:
	set(value):
		if value:
			call_deferred("rebuild")

@export var add_corridor: bool = true

var _generated: Node3D


func _ready() -> void:
	rebuild()


func rebuild() -> void:
	# 清除旧内容
	if _generated:
		remove_child(_generated)
		_generated.queue_free()
	
	_generated = Node3D.new()
	_generated.name = "Generated"
	add_child(_generated)
	
	# 创建走廊
	if add_corridor:
		_build_corridor()
	
	# 排列所有房间（走廊两侧）
	var room_index := 0
	for i in range(ROOM_SCENES.size()):
		var scene := ROOM_SCENES[i]
		var room := scene.instantiate() as Node3D
		
		# 计算位置：左侧和右侧交替
		var side := 1 if i % 2 == 0 else -1
		var row := i / 2
		
		var room_pos := Vector3(
			side * (D.CORRIDOR_WIDTH / 2.0 + D.ACTIVITY_DEPTH / 2.0),
			0.0,
			-row * D.CELL_PITCH
		)
		
		# 删除房间里的墙（如果还有）
		_remove_walls(room)
		
		# 为房间添加标准尺寸的墙（后墙+左墙+右墙）
		_add_standard_walls(room, room_pos, side)
		
		room.position = room_pos
		_generated.add_child(room)
		room_index += 1
	
	# 添加相机
	_add_camera()
	
	print("✓ 生成完整宿舍，共 %d 个房间" % room_index)


func _build_corridor() -> void:
	"""创建中央走廊"""
	# 走廊地板
	var corridor_floor := MeshInstance3D.new()
	corridor_floor.name = "CorridorFloor"
	corridor_floor.mesh = BoxMesh.new()
	corridor_floor.mesh.size = Vector3(
		D.CORRIDOR_WIDTH,
		0.1,
		ROOM_SCENES.size() / 2 * D.CELL_PITCH
	)
	corridor_floor.position = Vector3(
		0.0,
		0.05,
		-(ROOM_SCENES.size() / 2 - 1) * D.CELL_PITCH / 2.0
	)
	var floor_mat := StandardMaterial3D.new()
	floor_mat.albedo_color = D.CORRIDOR_COLOR
	corridor_floor.surface_material_override/0 = floor_mat
	_generated.add_child(corridor_floor)
	
	# 走廊天花板
	var corridor_ceiling := MeshInstance3D.new()
	corridor_ceiling.name = "CorridorCeiling"
	corridor_ceiling.mesh = BoxMesh.new()
	corridor_ceiling.mesh.size = Vector3(
		D.CORRIDOR_WIDTH,
		0.1,
		ROOM_SCENES.size() / 2 * D.CELL_PITCH
	)
	corridor_ceiling.position = Vector3(
		0.0,
		D.WALL_HEIGHT - 0.05,
		-(ROOM_SCENES.size() / 2 - 1) * D.CELL_PITCH / 2.0
	)
	var ceiling_mat := StandardMaterial3D.new()
	ceiling_mat.albedo_color = Color(0.9, 0.9, 0.9)
	corridor_ceiling.surface_material_override/0 = ceiling_mat
	_generated.add_child(corridor_ceiling)


func _add_camera() -> void:
	var camera := Camera3D.new()
	camera.name = "Camera3D"
	camera.position = Vector3(0, 15, 15)
	camera.look_at(Vector3(0, 0, -10))
	_generated.add_child(camera)
	
	# 添加环境光
	var light := OmniLight3D.new()
	light.name = "OmniLight3D"
	light.position = Vector3(0, 10, 0)
	light.light_energy = 2.0
	_generated.add_child(light)


func _remove_walls(room: Node3D) -> void:
	"""删除房间里的墙节点"""
	var to_remove := []
	_find_walls(room, to_remove)
	
	for wall in to_remove:
		wall.get_parent().remove_child(wall)
		wall.queue_free()


func _find_walls(node: Node, to_remove: Array) -> void:
	"""递归查找所有墙节点"""
	var name_lower := node.name.to_lower()
	
	# 检查节点名是否包含 wall
	if name_lower.contains("wall") or name_lower.contains("floor"):
		to_remove.append(node)
		return
	
	# 递归检查子节点
	for child in node.get_children():
		_find_walls(child, to_remove)


func _add_standard_walls(room: Node3D, room_pos: Vector3, side: int) -> void:
	"""为房间添加标准尺寸的墙"""
	var walls := Node3D.new()
	walls.name = "StandardWalls"
	
	# 后墙（青色半透明）
	var back_wall := MeshInstance3D.new()
	back_wall.name = "BackWall"
	back_wall.mesh = BoxMesh.new()
	back_wall.mesh.size = Vector3(0.1, D.WALL_HEIGHT, D.CELL_PITCH)
	back_wall.position = Vector3(-D.ACTIVITY_DEPTH / 2.0, D.WALL_HEIGHT / 2.0, 0.0)
	var back_mat := StandardMaterial3D.new()
	back_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	back_mat.albedo_color = Color(0, 0.8, 1, 0.5)
	back_wall.surface_material_override/0 = back_mat
	walls.add_child(back_wall)
	
	# 侧墙1（橙色半透明）
	var side_wall_1 := MeshInstance3D.new()
	side_wall_1.name = "SideWall1"
	side_wall_1.mesh = BoxMesh.new()
	side_wall_1.mesh.size = Vector3(D.ACTIVITY_DEPTH, D.WALL_HEIGHT, 0.1)
	side_wall_1.position = Vector3(0.0, D.WALL_HEIGHT / 2.0, D.CELL_PITCH / 2.0)
	var side_mat_1 := StandardMaterial3D.new()
	side_mat_1.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	side_mat_1.albedo_color = Color(1, 0.5, 0, 0.5)
	side_wall_1.surface_material_override/0 = side_mat_1
	walls.add_child(side_wall_1)
	
	# 侧墙2（绿色半透明）
	var side_wall_2 := MeshInstance3D.new()
	side_wall_2.name = "SideWall2"
	side_wall_2.mesh = BoxMesh.new()
	side_wall_2.mesh.size = Vector3(D.ACTIVITY_DEPTH, D.WALL_HEIGHT, 0.1)
	side_wall_2.position = Vector3(0.0, D.WALL_HEIGHT / 2.0, -D.CELL_PITCH / 2.0)
	var side_mat_2 := StandardMaterial3D.new()
	side_mat_2.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	side_mat_2.albedo_color = Color(0, 1, 0.5, 0.5)
	side_wall_2.surface_material_override/0 = side_mat_2
	walls.add_child(side_wall_2)
	
	room.add_child(walls)