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
		
		room.position = Vector3(
			side * (D.CORRIDOR_WIDTH / 2.0 + D.ACTIVITY_DEPTH / 2.0),
			0.0,
			-row * D.CELL_PITCH
		)
		
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