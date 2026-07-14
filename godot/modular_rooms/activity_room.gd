@tool
class_name ModularActivityRoom
extends Node3D

const D := preload("res://modular_rooms/room_dimensions.gd")
const G := preload("res://modular_rooms/modular_geometry.gd")
const ACTIVITY_SCENES := [
	preload("res://room/common_area/1_kitchen_room.tscn"),
	preload("res://room/common_area/2_sitting_room.tscn"),
	preload("res://room/common_area/3_media_room.tscn"),
	preload("res://room/common_area/4_gym.tscn"),
	preload("res://room/common_area/5_garden.tscn"),
	preload("res://room/common_area/6_working_room.tscn"),
	preload("res://room/common_area/7_music_room.tscn"),
	preload("res://room/common_area/8_bookroom.tscn"),
]
const ARCHITECTURAL_NODES := ["Walls", "Walls1", "Walls2", "Walls3", "Flooring", "Carpet", "floor", "ground"]
const WALL_CONTACT_GAP: float = 0.001
const TARGET_X_MIN: float = -D.ACTIVITY_DEPTH / 2.0 + 0.062
const TARGET_X_MAX: float = D.ACTIVITY_DEPTH / 2.0
const TARGET_Z_MIN: float = -D.CELL_PITCH / 2.0 + 0.062
const TARGET_Z_MAX: float = D.CELL_PITCH / 2.0 - 0.062

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
	var furniture_root := Node3D.new()
	furniture_root.name = "SourceFurniture"
	_generated.add_child(furniture_root)
	var source_room := ACTIVITY_SCENES[kind % ACTIVITY_SCENES.size()].instantiate() as Node3D
	source_room.name = "SourceRoom"
	furniture_root.add_child(source_room)
	_hide_unwanted_furniture(source_room, kind)

	# Fit using the authored room shell so wall-anchored furniture keeps its original relationship.
	source_room.force_update_transform()
	var source_envelope := G.visual_bounds_in(source_room, furniture_root)
	_hide_source_architecture(source_room)
	source_room.force_update_transform()
	var depth_scale := (D.ACTIVITY_DEPTH - 0.12) / source_envelope.size.x
	var width_scale := (D.CELL_PITCH - 0.24) / source_envelope.size.z
	var uniform_scale := minf(depth_scale, width_scale)
	var fit_scale := Vector3.ONE * uniform_scale
	if kind % ACTIVITY_SCENES.size() == 4:
		var finish_depth := D.WALL_THICKNESS / 2.0 + G.FINISH_AIR_GAP + G.FINISH_THICKNESS
		depth_scale = (D.ACTIVITY_DEPTH - finish_depth - WALL_CONTACT_GAP) / source_envelope.size.x
		width_scale = (D.CELL_PITCH - 2.0 * (finish_depth + WALL_CONTACT_GAP)) / source_envelope.size.z
		fit_scale = Vector3(depth_scale, 1.0, width_scale)
	source_room.scale *= fit_scale
	source_room.force_update_transform()
	_apply_physical_dimensions(source_room, furniture_root, kind, fit_scale)
	var fitted_envelope := AABB(
		source_envelope.position * fit_scale,
		source_envelope.size * fit_scale
	)
	var fitted_furniture_bounds := G.visual_bounds_in(source_room, furniture_root)
	source_room.position = Vector3(
		-D.ACTIVITY_DEPTH / 2.0 + 0.06 - fitted_envelope.position.x,
		0.01 - fitted_furniture_bounds.position.y,
		-fitted_envelope.get_center().z
	)
	source_room.force_update_transform()
	_apply_wall_anchors(source_room, furniture_root, kind)
	_apply_layout_corrections(source_room, furniture_root, kind)
	_add_source_colliders(source_room)


func _apply_physical_dimensions(source_room: Node3D, reference: Node3D, kind: int, fit_scale: Vector3) -> void:
	var content := _content_root(source_room)
	match kind % ACTIVITY_SCENES.size():
		0:
			for node_name in ["Top_Shelf", "Pan_Shelf", "Book110", "Book210", "Counter", "Recycling_Bins", "Refrigerator", "Picture5", "Dinner_Table"]:
					_scale_uniform(content, node_name, reference, 1.0 / fit_scale.x)
			_scale_height(content, "Shelves", reference, 1.631)
			_scale_height(content, "Dinner_Table", reference, 0.75)
		1:
			_scale_height(content, "Table", reference, 0.75)
			for chair_index in range(1, 9):
				_scale_height(content, "Chair%d" % chair_index, reference, 0.82)
		2:
			_scale_footprint_long_edge(content, "Coffee_Table", reference, 1.25)
		3:
			_scale_footprint_long_edge(content, "Treadmill", reference, 1.70)
			_scale_footprint_long_edge(content, "Treadmill2", reference, 1.70)
			_scale_footprint_long_edge(content, "YogaBall", reference, 0.72)
			_scale_footprint_long_edge(content, "YogaBall1", reference, 0.72)
		5:
			for table_name in ["Table", "Table2"]:
				_scale_height(content, table_name, reference, 0.74)
			for chair_name in ["Chair", "Chair2"]:
				_scale_height(content, chair_name, reference, 0.98)
		6:
			_scale_footprint_long_edge(content, "music_set", reference, 3.0)
			_scale_footprint_long_edge(content, "Drum_kit", reference, 1.75)
			_scale_footprint_long_edge(content, "piano", reference, 1.35)
		7:
			_scale_height(content, "Table", reference, 0.74)
			for chair_index in range(1, 7):
				_scale_height(content, "Chair%d" % chair_index, reference, 0.82)
	source_room.force_update_transform()


func _scale_uniform(content: Node3D, node_name: String, reference: Node3D, factor: float) -> void:
	var node := content.get_node_or_null(NodePath(node_name)) as Node3D
	if node == null:
		return
	var previous_bounds := G.visual_bounds_in(node, reference)
	node.scale *= factor
	node.force_update_transform()
	_restore_visual_anchor(node, reference, previous_bounds)


func _scale_height(content: Node3D, node_name: String, reference: Node3D, target_height: float) -> void:
	var node := content.get_node_or_null(NodePath(node_name)) as Node3D
	if node == null:
		return
	var bounds := G.visual_bounds_in(node, reference)
	if bounds.size.y <= 0.001:
		return
	var adjusted_scale := node.scale
	adjusted_scale.y *= target_height / bounds.size.y
	node.scale = adjusted_scale
	node.force_update_transform()
	_restore_visual_anchor(node, reference, bounds)


func _scale_footprint_long_edge(content: Node3D, node_name: String, reference: Node3D, target_length: float) -> void:
	var node := content.get_node_or_null(NodePath(node_name)) as Node3D
	if node == null:
		return
	var bounds := G.visual_bounds_in(node, reference)
	var current_length := maxf(bounds.size.x, bounds.size.z)
	if current_length <= 0.001:
		return
	node.scale *= target_length / current_length
	node.force_update_transform()
	_restore_visual_anchor(node, reference, bounds)


func _scale_axis_length(content: Node3D, node_name: String, reference: Node3D, axis: int, target_length: float) -> void:
	var node := content.get_node_or_null(NodePath(node_name)) as Node3D
	if node == null:
		return
	var bounds := G.visual_bounds_in(node, reference)
	var current_length := bounds.size[axis]
	if current_length <= 0.001:
		return
	var adjusted_scale := node.scale
	adjusted_scale[axis] *= target_length / current_length
	node.scale = adjusted_scale
	node.force_update_transform()
	_restore_visual_anchor(node, reference, bounds)


func _shift_axis_to_center(content: Node3D, node_name: String, reference: Node3D, axis: int, target_center: float) -> void:
	var node := content.get_node_or_null(NodePath(node_name)) as Node3D
	if node == null:
		return
	var bounds := G.visual_bounds_in(node, reference)
	var local_delta := Vector3.ZERO
	local_delta[axis] = target_center - bounds.get_center()[axis]
	var global_delta := reference.to_global(local_delta) - reference.to_global(Vector3.ZERO)
	node.global_position += global_delta
	node.force_update_transform()


func _restore_visual_anchor(node: Node3D, reference: Node3D, previous_bounds: AABB) -> void:
	var current_bounds := G.visual_bounds_in(node, reference)
	var previous_anchor := Vector3(
		previous_bounds.get_center().x,
		previous_bounds.position.y,
		previous_bounds.get_center().z
	)
	var current_anchor := Vector3(
		current_bounds.get_center().x,
		current_bounds.position.y,
		current_bounds.get_center().z
	)
	var local_delta := previous_anchor - current_anchor
	var global_delta := reference.to_global(local_delta) - reference.to_global(Vector3.ZERO)
	node.global_position += global_delta
	node.force_update_transform()


func _apply_wall_anchors(source_room: Node3D, reference: Node3D, kind: int) -> void:
	var content := _content_root(source_room)
	var groups: Array = []
	match kind % ACTIVITY_SCENES.size():
		0:
			groups = [
				[["Top_Shelf"], "x_min"], [["Pan_Shelf"], "x_min"],
				[["Counter"], "x_min"], [["Refrigerator"], "x_min"],
				[["Picture5"], "x_min"], [["Recycling_Bins"], "z_max"],
			]
		1:
			groups = [
				[["Pictures"], "z_max"], [["Pictures2"], "z_min"],
				[["Wall_Shelves"], "x_min"],
			]
		2:
			groups = [
				[["Pictures2"], "x_min"], [["TV_Dresser"], "z_max"],
				[["Plant"], "z_max"],
			]
		3:
			groups = [
				[["Dumbell_Shelf"], "x_min"], [["TV1"], "z_min"],
				[["Cork_Board"], "z_min"], [["Post_Its"], "z_min"],
				[["Shelf"], "z_max"],
			]
		4:
			groups = [[ ["jardi"], "x_min" ]]
		5:
			groups = [
				[["Wall_Shelves", "Books"], "z_min"],
				[["Boards"], "z_max"], [["Table", "PC_Setup"], "x_min"],
				[["Table3"], "x_min"],
			]
		7:
			groups = [
				[["Bookshelf1"], "z_max"], [["Bookshelf2"], "x_min"],
				[["Bookshelf3"], "z_min"], [["Bookshelf4"], "z_min"],
			]
	for group in groups:
		_snap_group_to_wall(content, group[0], String(group[1]), reference)
	source_room.force_update_transform()


func _snap_group_to_wall(content: Node3D, node_names: Array, wall: String, reference: Node3D) -> void:
	var nodes: Array[Node3D] = []
	var has_bounds := false
	var bounds := AABB()
	for node_name in node_names:
		var node := content.get_node_or_null(NodePath(String(node_name))) as Node3D
		if node == null:
			continue
		var node_bounds := G.visual_bounds_in(node, reference)
		bounds = bounds.merge(node_bounds) if has_bounds else node_bounds
		has_bounds = true
		nodes.append(node)
	if not has_bounds:
		return
	var delta := Vector3.ZERO
	match wall:
		"x_min": delta.x = TARGET_X_MIN + WALL_CONTACT_GAP - bounds.position.x
		"x_max": delta.x = TARGET_X_MAX - WALL_CONTACT_GAP - bounds.end.x
		"z_min": delta.z = TARGET_Z_MIN + WALL_CONTACT_GAP - bounds.position.z
		"z_max": delta.z = TARGET_Z_MAX - WALL_CONTACT_GAP - bounds.end.z
	var global_delta := reference.to_global(delta) - reference.to_global(Vector3.ZERO)
	for node in nodes:
		node.global_position += global_delta


func _apply_layout_corrections(source_room: Node3D, reference: Node3D, kind: int) -> void:
	var content := _content_root(source_room)
	match kind % ACTIVITY_SCENES.size():
		0:
			# Keep the three large kitchen groups in separate depth bands.
			_scale_axis_length(content, "Shelves", reference, 0, 2.4)
			_scale_axis_length(content, "Shelves", reference, 2, 2.4)
			_snap_group_to_wall(content, ["Shelves"], "x_max", reference)
			_shift_axis_to_center(content, "Shelves", reference, 2, -1.4)
			_shift_axis_to_center(content, "Refrigerator", reference, 2, -0.55)
			_shift_axis_to_center(content, "Recycling_Bins", reference, 0, 1.48)
		3:
			# The two balls are loose props and must not share the same footprint.
			var first_ball := G.visual_bounds_in(content.get_node("YogaBall") as Node3D, reference)
			var second_ball := G.visual_bounds_in(content.get_node("YogaBall1") as Node3D, reference)
			if _overlap_size(first_ball, second_ball).z > 0.0:
				_shift_axis_to_center(content, "YogaBall1", reference, 2, second_ball.get_center().z + _overlap_size(first_ball, second_ball).z + 0.08)


func _overlap_size(first: AABB, second: AABB) -> Vector3:
	return Vector3(
		minf(first.end.x, second.end.x) - maxf(first.position.x, second.position.x),
		minf(first.end.y, second.end.y) - maxf(first.position.y, second.position.y),
		minf(first.end.z, second.end.z) - maxf(first.position.z, second.position.z)
	)


func _content_root(source_room: Node3D) -> Node3D:
	var converted := source_room.get_node_or_null("convert_node") as Node3D
	if converted != null:
		return converted
	var music_room := source_room.get_node_or_null("Room3") as Node3D
	return music_room if music_room != null else source_room


func _hide_source_architecture(source_room: Node3D) -> void:
	_hide_source_architecture_in(source_room)


func _hide_source_architecture_in(node: Node) -> void:
	for child in node.get_children():
		if child is Node3D and ARCHITECTURAL_NODES.has(String(child.name)):
			(child as Node3D).visible = false
		else:
			_hide_source_architecture_in(child)


func _hide_unwanted_furniture(source_room: Node3D, kind: int) -> void:
	if kind % ACTIVITY_SCENES.size() != 5:
		return
	var curtains := _content_root(source_room).get_node_or_null("Curtains") as Node3D
	if curtains != null:
		curtains.visible = false


func _add_source_colliders(source_room: Node3D) -> void:
	for child in source_room.get_children():
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
