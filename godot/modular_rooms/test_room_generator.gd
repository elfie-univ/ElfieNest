@tool
extends Node3D

## 测试房间生成器
## 实例化所有8个修改后的房间场景进行测试

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
	"Kitchen",
	"Sitting",
	"Media",
	"Gym",
	"Garden",
	"Working",
	"Music",
	"Bookroom",
]

@export_range(0, 7, 1) var preview_room_index: int = 0
@export var spacing: float = 10.0

var _generated: Node3D


func _ready() -> void:
	_generate_room(preview_room_index)


func _generate_room(index: int) -> void:
	_generated = _replace_generated()
	
	var room_scene := load(ROOM_PATHS[index % ROOM_PATHS.size()]) as PackedScene
	var room := room_scene.instantiate() as Node3D
	room.name = ROOM_NAMES[index]
	_generated.add_child(room)
	
	# 添加标签
	var label := Label3D.new()
	label.text = "%s Room (%d)" % [ROOM_NAMES[index], index + 1]
	label.position = Vector3(0, 5, 0)
	label.font_size = 64
	label.modulate = Color(1, 1, 0)
	_generated.add_child(label)


func _replace_generated() -> Node3D:
	var previous := get_node_or_null("Generated")
	if previous != null:
		remove_child(previous)
		previous.queue_free()
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)
	return generated