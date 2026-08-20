@tool
class_name ModularActivityRoom
extends Node3D

const D := preload("res://rooms/room_dimensions.gd")
const G := preload("res://rooms/room_geometry.gd")
const ART := preload("res://rooms/assets/artwork/artwork_gallery.gd")
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
const ACTIVITY_CAMERA_Y: float = 1.35
const ACTIVITY_CAMERA_TARGET_Y: float = 0.85
const KITCHEN_SCENE_INDEX: int = 0
const KITCHEN_CAMERA_POSITION := Vector3(1.30, 1.45, 0.70)
const KITCHEN_CAMERA_TARGET := Vector3(0.25, 0.85, -1.10)
@export var auto_preview: bool = true
@export var preview_theme_color := Color("#ef8354")
@export_range(0, 7, 1) var preview_furniture_kind: int = 0

var _generated: Node3D
var _observation_target_local := Vector3.ZERO


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
	_observation_target_local = _camera_target_for(furniture_kind)
	_build_interior_light()
	var camera_anchor := Marker3D.new()
	camera_anchor.name = "CameraAnchor"
	camera_anchor.position = _camera_position_for(furniture_kind)
	_generated.add_child(camera_anchor)
	camera_anchor.look_at(
		_generated.to_global(_observation_target_local), Vector3.UP
	)


func observation_target_local() -> Vector3:
	return _observation_target_local


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
	if scene_index == 1:
		_apply_gallery_art(source_room, ART.LIVING_ROOM_ART)
	elif scene_index == 2:
		_apply_gallery_art(source_room, ART.TV_ROOM_ART)
	_add_source_colliders(source_room)


func _camera_position_for(furniture_kind: int) -> Vector3:
	if _scene_index(furniture_kind) == KITCHEN_SCENE_INDEX:
		return KITCHEN_CAMERA_POSITION
	return Vector3(-D.ACTIVITY_DEPTH / 2.0 + 0.18, ACTIVITY_CAMERA_Y, 0.0)


func _camera_target_for(furniture_kind: int) -> Vector3:
	if _scene_index(furniture_kind) == KITCHEN_SCENE_INDEX:
		return KITCHEN_CAMERA_TARGET
	return Vector3(0.1, ACTIVITY_CAMERA_TARGET_Y, 0.0)


func _scene_index(furniture_kind: int) -> int:
	return posmod(furniture_kind, ACTIVITY_SCENES.size())


func _apply_gallery_art(source_room: Node3D, textures: Array[Texture2D]) -> void:
	var frames: Array[MeshInstance3D] = []
	_collect_picture_frames(source_room, frames)
	frames.sort_custom(func(left: MeshInstance3D, right: MeshInstance3D) -> bool:
		return str(left.get_path()) < str(right.get_path())
	)
	for index in range(frames.size()):
		_add_artwork_surface(frames[index], textures[index % textures.size()], index)


func _collect_picture_frames(node: Node, frames: Array[MeshInstance3D]) -> void:
	for child in node.get_children():
		var mesh_instance := child as MeshInstance3D
		if mesh_instance != null and mesh_instance.name.begins_with("Picture"):
			frames.append(mesh_instance)
		_collect_picture_frames(child, frames)


func _add_artwork_surface(frame: MeshInstance3D, texture: Texture2D, index: int) -> void:
	var bounds := frame.get_aabb()
	var depth_axis := _smallest_axis(bounds.size)
	var plane_axes := [0, 1, 2]
	plane_axes.erase(depth_axis)
	var vertical_axis: int = plane_axes[0]
	if _axis_world_alignment(frame, plane_axes[1], Vector3.UP) > _axis_world_alignment(frame, vertical_axis, Vector3.UP):
		vertical_axis = plane_axes[1]
	var horizontal_axis: int = plane_axes[1] if plane_axes[0] == vertical_axis else plane_axes[0]

	var room_center_local := frame.to_local(_generated.global_position)
	var center := bounds.get_center()
	var inward_sign := signf(room_center_local[depth_axis] - center[depth_axis])
	if is_zero_approx(inward_sign):
		inward_sign = 1.0
	var inward := _axis_vector(depth_axis) * inward_sign
	var vertical := _axis_vector(vertical_axis)
	if (frame.global_transform.basis * vertical).dot(Vector3.UP) < 0.0:
		vertical = -vertical
	var horizontal := vertical.cross(inward).normalized()

	var available_width := bounds.size[horizontal_axis] * 0.82
	var available_height := bounds.size[vertical_axis] * 0.82
	var horizontal_scale := (frame.global_transform.basis * horizontal).length()
	var vertical_scale := (frame.global_transform.basis * vertical).length()
	var physical_width := available_width * horizontal_scale
	var physical_height := available_height * vertical_scale
	var texture_aspect := float(texture.get_width()) / float(texture.get_height())
	if physical_width / physical_height > texture_aspect:
		available_width = physical_height * texture_aspect / horizontal_scale
	else:
		available_height = physical_width / texture_aspect / vertical_scale

	var quad := QuadMesh.new()
	quad.size = Vector2(available_width, available_height)
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	quad.material = material

	var artwork := MeshInstance3D.new()
	artwork.name = "GalleryArtwork_%02d" % index
	artwork.mesh = quad
	artwork.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var face_position := center
	face_position[depth_axis] += inward_sign * (bounds.size[depth_axis] / 2.0 + 0.02)
	artwork.transform = Transform3D(Basis(horizontal, vertical, inward), face_position)
	frame.add_child(artwork)


func _smallest_axis(size: Vector3) -> int:
	var axis := 0
	if size.y < size[axis]:
		axis = 1
	if size.z < size[axis]:
		axis = 2
	return axis


func _axis_world_alignment(node: Node3D, axis: int, direction: Vector3) -> float:
	return absf((node.global_transform.basis * _axis_vector(axis)).normalized().dot(direction))


func _axis_vector(axis: int) -> Vector3:
	if axis == 0:
		return Vector3.RIGHT
	if axis == 1:
		return Vector3.UP
	return Vector3.BACK


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
