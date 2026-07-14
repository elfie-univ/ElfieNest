@tool
extends Node3D

## 最终房间预览 - 直接加载修改后的房间场景

const ROOM_PATHS := [
	"res://modular_rooms/common_area/1_kitchen_room.tscn",
	"res://modular_rooms/common_area/2_sitting_room.tscn",
	"res://modular_rooms/common_area/3_media_room.tscn",
	"res://modular_rooms/common_area/4_gym.tscn",
	"res://modular_rooms/common_area/5_garden.tscn",
	"res://modular_rooms/common_area/6_working_room.tscn",
	"res://modular_rooms/common_area/7_music_room.tscn",
	"res://modular_rooms/common_area/8_bookroom.tscn",
]

const ROOM_NAMES := [
	"Kitchen (厨房)",
	"Sitting (客厅)",
	"Media (影音室)",
	"Gym (健身房)",
	"Garden (花园)",
	"Working (工作室)",
	"Music (音乐室)",
	"Bookroom (书房)",
]

@export_range(0, 7, 1) var preview_room_index: int = 0:
	set(value):
		preview_room_index = value
		if Engine.is_editor_hint():
			_load_room()

@export var show_all: bool = false:
	set(value):
		show_all = value
		if Engine.is_editor_hint():
			_load_all_rooms()

var _current_room: Node3D


func _ready() -> void:
	if Engine.is_editor_hint():
		_load_room()
	else:
		_load_room()


func _load_room() -> void:
	# 清除当前房间
	if _current_room:
		remove_child(_current_room)
		_current_room.queue_free()
	
	# 清除所有子节点（除了相机）
	for child in get_children():
		if child.name != "Camera3D":
			remove_child(child)
			child.queue_free()
	
	# 加载房间
	var room_scene := load(ROOM_PATHS[preview_room_index]) as PackedScene
	if room_scene:
		_current_room = room_scene.instantiate() as Node3D
		_current_room.name = "Room"
		add_child(_current_room)
		print("✓ 加载房间: %s" % ROOM_NAMES[preview_room_index])
	else:
		push_error("✗ 无法加载房间: %s" % ROOM_PATHS[preview_room_index])


func _load_all_rooms() -> void:
	# 清除所有
	for child in get_children():
		if child.name != "Camera3D":
			remove_child(child)
			child.queue_free()
	
	var spacing := 10.0
	var offset_z := 0.0
	
	for i in range(ROOM_PATHS.size()):
		var room_scene := load(ROOM_PATHS[i]) as PackedScene
		if room_scene:
			var room := room_scene.instantiate() as Node3D
			room.position.z = offset_z
			room.name = ROOM_NAMES[i]
			add_child(room)
			offset_z += spacing
			print("✓ 加载房间: %s" % ROOM_NAMES[i])