@tool
class_name ModularActivityRoom
extends Node3D

const D := preload("res://rooms/room_dimensions.gd")
const G := preload("res://rooms/room_geometry.gd")
const ACTIVITY_SCENES := [
	preload("res://rooms/common_area_layouts/kitchen_layout.tscn"),
	preload("res://rooms/common_area_layouts/sitting_layout.tscn"),
	preload("res://rooms/common_area_layouts/media_layout.tscn"),
	preload("res://rooms/common_area_layouts/gym_layout.tscn"),
	preload("res://rooms/common_area_layouts/garden_layout.tscn"),
	preload("res://rooms/common_area_layouts/working_layout.tscn"),
	preload("res://rooms/common_area_layouts/music_layout.tscn"),
	preload("res://rooms/common_area_layouts/bookroom_layout.tscn"),
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
	G.add_floor(_generated, "ActivityFloor", D.ACTIVITY_DEPTH, D.CELL_PITCH, Vector3.ZERO, theme_color)
	G.add_wall(
		_generated,
		"OuterWall",
		Vector3(D.WALL_THICKNESS, D.WALL_HEIGHT, D.CELL_PITCH),
		Vector3(-D.ACTIVITY_DEPTH / 2.0, D.WALL_HEIGHT / 2.0, 0.0),
		D.EXTERIOR_COLOR,
		theme_color
	)
	_build_furniture(furniture_kind)
	_build_interior_light()
	var camera_anchor := Marker3D.new()
	camera_anchor.name = "CameraAnchor"
	camera_anchor.position = Vector3(D.ACTIVITY_DEPTH / 2.0 - 0.12, 2.55, 0.0)
	_generated.add_child(camera_anchor)
	camera_anchor.look_at(
		_generated.to_global(Vector3(0.1, 0.55, 0.0)), Vector3.UP
	)


func _build_interior_light() -> void:
	var light := OmniLight3D.new()
	light.name = "ActivityInteriorLight"
	light.position = Vector3(0.0, 2.55, 0.0)
	light.light_color = Color.WHITE
	light.light_energy = 0.8
	light.omni_range = 4.8
	light.shadow_enabled = false
	_generated.add_child(light)


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
	var furniture_root := Node3D.new()
	furniture_root.name = "SourceFurniture"
	_generated.add_child(furniture_root)
	var scene_index := kind % ACTIVITY_SCENES.size()
	var source_room := ACTIVITY_SCENES[scene_index].instantiate() as Node3D
	source_room.name = "SourceRoom"
	furniture_root.add_child(source_room)
	source_room.force_update_transform()
	_add_source_colliders(source_room)


func _content_root(source_room: Node3D) -> Node3D:
	var converted := source_room.get_node_or_null("convert_node") as Node3D
	if converted != null:
		return converted
	var music_room := source_room.get_node_or_null("Room3") as Node3D
	return music_room if music_room != null else source_room


func _add_source_colliders(source_room: Node3D) -> void:
	for child in _content_root(source_room).get_children():
		var furniture := child as Node3D
		if furniture == null or not furniture.visible or _is_decorative_node(furniture.name):
			continue
		G.add_visual_bounds_collision(_generated, "ActivityFurniture_%s" % furniture.name, furniture)


func _is_decorative_node(node_name: String) -> bool:
	return (
		node_name.begins_with("Picture")
		or node_name.begins_with("Post_Its")
		or node_name == "Carpet"
	)
