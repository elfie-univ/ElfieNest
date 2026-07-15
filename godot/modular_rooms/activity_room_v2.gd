@tool
class_name ModularActivityRoomV2
extends Node3D

## 新版活动房生成器
## 使用独立家具组合预制件，不再依赖完整房间场景

const D := preload("res://modular_rooms/room_dimensions.gd")
const G := preload("res://modular_rooms/modular_geometry.gd")

# 新的家具组合引用（用户拖拽完成后使用）
const FURNITURE_SETS := [
	preload("res://modular_rooms/assets/furniture_sets/kitchen_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/sitting_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/media_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/gym_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/garden_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/working_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/music_furniture_set.tscn"),
	preload("res://modular_rooms/assets/furniture_sets/bookroom_furniture_set.tscn"),
]

@export var auto_preview: bool = true
@export var preview_theme_color := Color("#ef8354")
@export_range(0, 7, 1) var preview_furniture_kind: int = 0

var _generated: Node3D


func _ready() -> void:
	if auto_preview:
		build(preview_theme_color, preview_furniture_kind)


func build(theme_color: Color, furniture_kind: int) -> void:
	_generated = _replace_generated()
	
	# 创建地板和墙壁
	G.add_floor(_generated, "ActivityFloor", D.ACTIVITY_DEPTH, D.CELL_PITCH, Vector3.ZERO, theme_color)
	G.add_wall(
		_generated,
		"OuterWall",
		Vector3(D.WALL_THICKNESS, D.WALL_HEIGHT, D.CELL_PITCH),
		Vector3(-D.ACTIVITY_DEPTH / 2.0, D.WALL_HEIGHT / 2.0, 0.0),
		D.EXTERIOR_COLOR,
		theme_color
	)
	
	# 加载家具组合
	_build_furniture(furniture_kind)
	
	# 添加相机锚点
	var camera_anchor := Marker3D.new()
	camera_anchor.name = "CameraAnchor"
	camera_anchor.position = Vector3(0.0, 7.0, 0.0)
	camera_anchor.rotation_degrees.x = -90.0
	_generated.add_child(camera_anchor)


func _replace_generated() -> Node3D:
	var previous := get_node_or_null("Generated")
	if previous != null:
		remove_child(previous)
		previous.queue_free()
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)
	return generated


func _build_furniture(kind: int) -> void:
	"""加载家具组合预制件"""
	var furniture_set := FURNITURE_SETS[kind % FURNITURE_SETS.size()].instantiate() as Node3D
	
	# 隐藏参考墙（如果存在）
	var reference_walls := furniture_set.get_node_or_null("ReferenceWalls")
	if reference_walls:
		reference_walls.queue_free()
	
	furniture_set.name = "FurnitureSet"
	_generated.add_child(furniture_set)
