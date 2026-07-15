@tool
class_name ModularDormRoom
extends Node3D

const D := preload("res://rooms/room_dimensions.gd")
const G := preload("res://rooms/room_geometry.gd")
const BED_SCENE := preload("res://rooms/assets/beds/base_bed.tscn")
const MURAL_TEXTURE := preload("res://rooms/assets/artwork/gallery/img1.jpg")
const DOOR_WIDTH: float = 1.4
const DOOR_HEIGHT: float = 2.2
const BED_CENTER_X: float = 0.937172
const BED_POSITIONS := [
	Vector3(-BED_CENTER_X, 0.02596, 1.80552),
	Vector3(BED_CENTER_X, 0.01137, 1.80449),
	Vector3(-BED_CENTER_X, 0.01998, -1.80779),
	Vector3(BED_CENTER_X, 0.00081, -1.78922),
]
const BED_ROTATIONS := [
	Vector3(0.0, 90.0, 180.0),
	Vector3(0.0, 90.0, 0.0),
	Vector3(0.0, -90.0, 0.0),
	Vector3(0.0, -90.0, -180.0),
]
const BED_SCALES := [
	Vector3(-0.7, -0.7, -0.7),
	Vector3(0.7, 0.7, 0.7),
	Vector3(0.7, 0.7, 0.7),
	Vector3(-0.7, -0.7, -0.7),
]
const WALL_CONTACT_GAP: float = 0.001
const ARTWORK_FRAME_GAP: float = 0.0005
const RUG_SURFACE_LEVELS := [0.0002, 0.0005, 0.0008]
@export var auto_preview: bool = true
@export_range(0, 99, 1) var preview_room_index: int = 0

var _generated: Node3D


func _ready() -> void:
	if auto_preview:
		build(preview_room_index)


func build(room_index: int, occupied_bed_count: int = 4) -> void:
	_generated = _replace_generated()
	G.add_floor(_generated, "DormFloor", D.DORM_DEPTH, D.CELL_PITCH, Vector3.ZERO, D.DORM_FLOOR_COLOR)
	G.add_wall(
		_generated,
		"OuterWall",
		Vector3(D.WALL_THICKNESS, D.WALL_HEIGHT, D.CELL_PITCH),
		Vector3(D.DORM_DEPTH / 2.0, D.WALL_HEIGHT / 2.0, 0.0),
		D.DORM_WALL_COLOR,
		D.EXTERIOR_COLOR
	)
	_build_entryway()
	_build_beds(room_index, occupied_bed_count)
	_build_rug()
	_build_mural()
	_build_interior_light()
	var camera_anchor := Marker3D.new()
	camera_anchor.name = "CameraAnchor"
	camera_anchor.position = Vector3(0.0, 7.5, 0.0)
	camera_anchor.rotation_degrees.x = -90.0
	_generated.add_child(camera_anchor)


func _build_entryway() -> void:
	var side_length := (D.CELL_PITCH - DOOR_WIDTH) / 2.0
	var side_offset := DOOR_WIDTH / 2.0 + side_length / 2.0
	var door_room_face_x := -D.DORM_DEPTH / 2.0 + D.WALL_THICKNESS / 2.0 + G.FINISH_AIR_GAP + G.FINISH_THICKNESS
	var door_trim_air_gap := 0.002
	var door_track_depth := 0.075
	var door_header_depth := 0.055
	var door_track_height := 0.08
	var door_track_top_y := DOOR_HEIGHT - 0.02
	var door_header_bottom_y := door_track_top_y + 0.0005
	var door_header_top_y := DOOR_HEIGHT + G.FINISH_INSET / 2.0
	var door_header_height := door_header_top_y - door_header_bottom_y
	for z_position in [-side_offset, side_offset]:
		G.add_wall(
			_generated,
			"DormDoorwayLeft" if z_position < 0.0 else "DormDoorwayRight",
			Vector3(D.WALL_THICKNESS, D.WALL_HEIGHT, side_length),
			Vector3(-D.DORM_DEPTH / 2.0, D.WALL_HEIGHT / 2.0, z_position),
			D.CORRIDOR_WALL_COLOR,
			D.DORM_WALL_COLOR
		)
	var lintel_height := D.WALL_HEIGHT - DOOR_HEIGHT
	G.add_wall(
		_generated,
		"DormDoorwayLintel",
		Vector3(D.WALL_THICKNESS, lintel_height, DOOR_WIDTH),
		Vector3(-D.DORM_DEPTH / 2.0, DOOR_HEIGHT + lintel_height / 2.0, 0.0),
		D.CORRIDOR_WALL_COLOR,
		D.DORM_WALL_COLOR
	)
	var door_leaf_width := 0.58
	for z_position in [-0.99, 0.99]:
		G.add_box(
			_generated,
			"DormPocketDoorLeft" if z_position < 0.0 else "DormPocketDoorRight",
			Vector3(0.06, DOOR_HEIGHT - 0.1, door_leaf_width),
			Vector3(-D.DORM_DEPTH / 2.0 + 0.055, (DOOR_HEIGHT - 0.1) / 2.0, z_position),
			D.DORM_DOOR_COLOR,
			true
		)
	G.add_box(
		_generated,
		"DormDoorTrack",
		Vector3(door_track_depth, door_track_height, DOOR_WIDTH + 0.16),
		Vector3(door_room_face_x + door_trim_air_gap + door_track_depth / 2.0, door_track_top_y - door_track_height / 2.0, 0.0),
		Color("#a9977d")
	)
	G.add_box(
		_generated,
		"DormDoorHeaderTrim",
		Vector3(door_header_depth, door_header_height, DOOR_WIDTH + 0.22),
		Vector3(door_room_face_x + door_trim_air_gap + door_header_depth / 2.0, door_header_bottom_y + door_header_height / 2.0, 0.0),
		Color("#f1eadf")
	)


func _replace_generated() -> Node3D:
	var previous := get_node_or_null("Generated")
	if previous != null:
		remove_child(previous)
		previous.queue_free()
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)
	return generated


func _build_beds(room_index: int, occupied_bed_count: int) -> void:
	var beds: Array[Node3D] = []
	var positive_row: Array[Node3D] = []
	var negative_row: Array[Node3D] = []
	for index in range(mini(occupied_bed_count, BED_POSITIONS.size())):
		var bed := BED_SCENE.instantiate() as Node3D
		bed.name = "Bed_%02d" % (room_index * 4 + index + 1)
		bed.position = BED_POSITIONS[index]
		bed.rotation_degrees = BED_ROTATIONS[index]
		bed.scale = BED_SCALES[index]
		_generated.add_child(bed)
		beds.append(bed)
		if index < 2:
			positive_row.append(bed)
		else:
			negative_row.append(bed)
	_snap_bed_row_to_partition(positive_row, true)
	_snap_bed_row_to_partition(negative_row, false)
	for bed in beds:
		G.add_visual_bounds_collision(_generated, "%sFurniture" % bed.name, bed)


func _snap_bed_row_to_partition(beds: Array[Node3D], positive_side: bool) -> void:
	if beds.is_empty():
		return
	var row_bounds := G.visual_bounds_in(beds[0], _generated)
	for index in range(1, beds.size()):
		row_bounds = row_bounds.merge(G.visual_bounds_in(beds[index], _generated))
	var finish_depth := D.WALL_THICKNESS / 2.0 + G.FINISH_AIR_GAP + G.FINISH_THICKNESS
	var partition_face := D.CELL_PITCH / 2.0 - finish_depth
	var target_edge := partition_face - WALL_CONTACT_GAP if positive_side else -partition_face + WALL_CONTACT_GAP
	var current_edge := row_bounds.end.z if positive_side else row_bounds.position.z
	var delta_z := target_edge - current_edge
	for bed in beds:
		bed.position.z += delta_z
		bed.force_update_transform()


func _build_rug() -> void:
	G.add_box(
		_generated,
		"DormRug",
		Vector3(3.42, 0.024, 1.72),
		Vector3(0.0, RUG_SURFACE_LEVELS[0] - 0.024 / 2.0, 0.0),
		D.DORM_RUG_COLOR,
		false,
		0.0,
		0.52
	)
	G.add_box(
		_generated,
		"DormRugOuterTrim",
		Vector3(3.16, 0.027, 1.46),
		Vector3(0.0, RUG_SURFACE_LEVELS[1] - 0.027 / 2.0, 0.0),
		D.DORM_RUG_TRIM_COLOR,
		false,
		0.0,
		0.5
	)
	G.add_box(
		_generated,
		"DormRugInset",
		Vector3(2.94, 0.03, 1.24),
		Vector3(0.0, RUG_SURFACE_LEVELS[2] - 0.03 / 2.0, 0.0),
		Color("#566270"),
		false,
		0.0,
		0.56
	)


func _build_mural() -> void:
	var wall_x := D.DORM_DEPTH / 2.0
	var finish_depth := D.WALL_THICKNESS / 2.0 + G.FINISH_AIR_GAP + G.FINISH_THICKNESS
	var wall_finish_face_x := wall_x - finish_depth
	var frame_depth := 0.052
	var frame_center_x := wall_finish_face_x - WALL_CONTACT_GAP - frame_depth / 2.0
	G.add_box(
		_generated,
		"DormMuralFrame",
		Vector3(frame_depth, 1.62, 2.28),
		Vector3(frame_center_x, 1.62, 0.0),
		Color("#4c433b")
	)
	var mural := MeshInstance3D.new()
	mural.name = "DormMural"
	var quad := QuadMesh.new()
	quad.size = Vector2(2.04, 1.38)
	mural.mesh = quad
	mural.position = Vector3(frame_center_x - frame_depth / 2.0 - ARTWORK_FRAME_GAP, 1.62, 0.0)
	mural.rotation_degrees.y = 90.0
	var material := StandardMaterial3D.new()
	material.albedo_texture = MURAL_TEXTURE
	material.roughness = 0.62
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	mural.material_override = material
	_generated.add_child(mural)
	G.add_box(
		_generated,
		"DormMuralLight",
		Vector3(0.045, 0.045, 1.56),
		Vector3(wall_x - 0.16, 2.44, 0.0),
		Color("#f4ddb5"),
		false,
		1.1
	)


func _build_interior_light() -> void:
	var light := OmniLight3D.new()
	light.name = "DormInteriorLight"
	light.position = Vector3(0.0, 2.6, 0.0)
	light.light_color = Color.WHITE
	light.light_energy = 0.08
	light.omni_range = 4.2
	light.shadow_enabled = false
	_generated.add_child(light)
