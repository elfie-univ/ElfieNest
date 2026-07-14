@tool
extends Node3D

## 测试所有8个房间的生成
## 使用 activity_room_v2.gd 来生成

const ROOM_NAMES := [
	"Kitchen",
	"Sitting",
	"Media",
	"Gym",
	"Garden",
	"Working",
	"Music",
	"Bookroom",
]

@export_range(0, 7, 1) var preview_room_index: int = 0:
	set(value):
		preview_room_index = value
		if Engine.is_editor_hint():
			_generate_preview()

@export var regenerate: bool = false:
	set(value):
		if value and Engine.is_editor_hint():
			_generate_preview()


func _ready() -> void:
	if not Engine.is_editor_hint():
		_generate_preview()


func _generate_preview() -> void:
	# 清除之前的预览
	for child in get_children():
		if child.name != "Camera3D":
			remove_child(child)
			child.queue_free()
	
	# 创建房间生成器
	var room_generator := ModularActivityRoomV2.new()
	room_generator.name = ROOM_NAMES[preview_room_index]
	room_generator.auto_preview = true
	room_generator.preview_furniture_kind = preview_room_index
	room_generator.preview_theme_color = Color("#ef8354")
	add_child(room_generator)
	
	print("生成房间: %s" % ROOM_NAMES[preview_room_index])