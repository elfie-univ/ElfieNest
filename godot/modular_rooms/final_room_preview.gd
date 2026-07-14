@tool
extends Node3D

## 最终房间生成器 - 使用你修改后的完整房间场景
## 直接加载 common_area 下的房间，不做任何修改

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
	"厨房 (Kitchen)",
	"客厅 (Sitting)",
	"影音室 (Media)",
	"健身房 (Gym)",
	"花园 (Garden)",
	"工作室 (Working)",
	"音乐室 (Music)",
	"书房 (Bookroom)",
]

@export_range(0, 7, 1) var room_index: int = 0:
	set(value):
		room_index = value
		if Engine.is_editor_hint():
			_load_room()

@export var regenerate: bool = false:
	set(value):
		if value and Engine.is_editor_hint():
			_load_room()

var _room: Node3D


func _ready() -> void:
	_load_room()


func _load_room() -> void:
	# 清除旧房间
	if _room:
		_room.queue_free()
		_room = null
	
	for child in get_children():
		if child.name != "Camera3D" and child.name != "OmniLight3D":
			child.queue_free()
	
	# 加载房间
	var scene := load(ROOM_PATHS[room_index]) as PackedScene
	if not scene:
		push_error("无法加载房间: %s" % ROOM_PATHS[room_index])
		return
	
	_room = scene.instantiate() as Node3D
	add_child(_room)
	
	print("✓ 加载房间: %s" % ROOM_NAMES[room_index])