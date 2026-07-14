@tool
class_name ModularNest
extends Node3D

const D := preload("res://modular_rooms/room_dimensions.gd")
const G := preload("res://modular_rooms/modular_geometry.gd")
const ACTIVITY_ROOM_SCENE := preload("res://modular_rooms/activity_room.tscn")
const DORM_ROOM_SCENE := preload("res://modular_rooms/dorm_room.tscn")
const PORTAL_ROOM_SCENE := preload("res://modular_rooms/portal_room.tscn")
const MURAL_TEXTURE := preload("res://room/assets/framed_painting/imgs/img1.jpg")
const THEMES: Array[Color] = [
	Color("#ef8354"),
	Color("#3aa7a3"),
	Color("#e05263"),
	Color("#76a85b"),
]
const CAMERA_START_OFFSET := Vector3(12.5, 24.5, 16.0)
const CAMERA_ORBIT_SPEED: float = 0.008
const CAMERA_MIN_PITCH: float = deg_to_rad(12.0)
const CAMERA_MAX_PITCH: float = deg_to_rad(82.0)
const CAMERA_MIN_SIZE: float = 5.0
const CAMERA_MAX_SIZE: float = 120.0
const CAMERA_BOUNDS_MARGIN: float = 2.0

@export_range(1, 80, 1) var bed_count: int = 16:
	set(value):
		bed_count = clampi(value, 1, 80)
		if is_inside_tree():
			call_deferred("rebuild")

@export var activity_group_ids := PackedInt32Array([0, 0, 1, 2])

@export var regenerate_editor_preview: bool = false:
	set(value):
		regenerate_editor_preview = false
		if value and Engine.is_editor_hint() and is_inside_tree():
			call_deferred("rebuild")

var _rebuilding := false
var _camera_target := Vector3.ZERO
var _camera_default_target := Vector3.ZERO
var _camera_yaw: float = 0.0
var _camera_pitch: float = 0.0
var _camera_distance: float = CAMERA_START_OFFSET.length()
var _camera_default_distance: float = CAMERA_START_OFFSET.length()
var _camera_default_size: float = 22.0


func _ready() -> void:
	if Engine.is_editor_hint():
		rebuild()
	else:
		call_deferred("rebuild")


func _unhandled_input(event: InputEvent) -> void:
	if Engine.is_editor_hint():
		return
	var camera := get_node_or_null("Camera3D") as Camera3D
	if camera == null:
		return
	if event is InputEventMouseMotion:
		var mouse_motion := event as InputEventMouseMotion
		if mouse_motion.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_camera_yaw = wrapf(
				_camera_yaw - mouse_motion.relative.x * CAMERA_ORBIT_SPEED,
				-PI,
				PI
			)
			_camera_pitch = clampf(
				_camera_pitch - mouse_motion.relative.y * CAMERA_ORBIT_SPEED,
				CAMERA_MIN_PITCH,
				CAMERA_MAX_PITCH
			)
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
		elif mouse_motion.button_mask & MOUSE_BUTTON_MASK_RIGHT:
			var viewport_height := maxf(get_viewport().get_visible_rect().size.y, 1.0)
			var pan_scale := camera.size / viewport_height
			var camera_basis := camera.transform.basis
			_camera_target += (
				-camera_basis.x * mouse_motion.relative.x
				+ camera_basis.y * mouse_motion.relative.y
			) * pan_scale
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton:
		var mouse_button := event as InputEventMouseButton
		if not mouse_button.pressed:
			return
		if mouse_button.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera.size = clampf(camera.size * 0.9, CAMERA_MIN_SIZE, CAMERA_MAX_SIZE)
			get_viewport().set_input_as_handled()
		elif mouse_button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera.size = clampf(camera.size / 0.9, CAMERA_MIN_SIZE, CAMERA_MAX_SIZE)
			get_viewport().set_input_as_handled()
	elif event is InputEventKey:
		var key_event := event as InputEventKey
		if key_event.pressed and not key_event.echo and key_event.keycode in [KEY_R, KEY_HOME]:
			_reset_camera()
			get_viewport().set_input_as_handled()


func rebuild() -> void:
	if _rebuilding:
		return
	_rebuilding = true
	var previous := get_node_or_null("Generated")
	if previous != null:
		remove_child(previous)
		previous.queue_free()
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)

	var room_count := D.room_count_for_beds(bed_count)
	var themes := _themes_for_rooms(room_count)
	_build_floors(generated, room_count)
	_build_rooms(generated, room_count, themes)
	_build_activity_boundaries(generated, room_count, themes)
	_build_dorm_boundaries(generated, room_count)
	_build_end_wall(generated, room_count)
	_build_portal_room(generated)
	_update_camera(room_count)
	_rebuilding = false


func _build_floors(parent: Node3D, room_count: int) -> void:
	var building_length := float(room_count) * D.CELL_PITCH
	G.add_floor(parent, "CorridorFloor", D.CORRIDOR_WIDTH, building_length, Vector3(0.0, 0.0, -building_length / 2.0), D.CORRIDOR_COLOR)
	G.add_box(
		parent,
		"CorridorCentralMarble",
		Vector3(1.88, 0.024, building_length - 0.16),
		Vector3(0.0, 0.014, -building_length / 2.0),
		Color("#d7dddd"),
		false,
		0.0,
		0.28
	)
	for side in [-1.0, 1.0]:
		G.add_box(
			parent,
			"CorridorWarmMarbleInlayLeft" if side < 0.0 else "CorridorWarmMarbleInlayRight",
			Vector3(0.08, 0.026, building_length - 0.16),
			Vector3(side, 0.016, -building_length / 2.0),
			Color("#827265"),
			false,
			0.0,
			0.3
		)
		G.add_box(
			parent,
			"CorridorDarkMarbleBandLeft" if side < 0.0 else "CorridorDarkMarbleBandRight",
			Vector3(0.28, 0.027, building_length - 0.16),
			Vector3(side * 1.18, 0.017, -building_length / 2.0),
			Color("#454b4c"),
			false,
			0.0,
			0.25
		)
		G.add_box(
			parent,
			"CorridorOuterMarbleBorderLeft" if side < 0.0 else "CorridorOuterMarbleBorderRight",
			Vector3(0.16, 0.024, building_length - 0.16),
			Vector3(side * 1.42, 0.014, -building_length / 2.0),
			D.CORRIDOR_WALL_COLOR,
			false,
			0.0,
			0.34
		)
	for index in range(room_count):
		_add_corridor_bay(parent, index, D.cell_center_z(index))


func _add_corridor_bay(parent: Node3D, index: int, center_z: float) -> void:
	for joint_index in range(2):
		var direction := -1.0 if joint_index == 0 else 1.0
		var z_position := center_z + direction * (D.CELL_PITCH / 2.0 - 0.08)
		G.add_box(
			parent,
			"CorridorCentralTileJoint_%02d_%d" % [index, joint_index],
			Vector3(1.88, 0.027, 0.028),
			Vector3(0.0, 0.028, z_position),
			Color("#b6bfbe"),
			false,
			0.0,
			0.3
		)
	var vein_x := -0.34 if index % 2 == 0 else 0.41
	G.add_box(
		parent,
		"CorridorMarbleVein_%02d" % index,
		Vector3(0.024, 0.028, 1.46),
		Vector3(vein_x, 0.029, center_z),
		Color("#c1c9c7"),
		false,
		0.0,
		0.34
	)
	G.add_box(
		parent,
		"DormDoorwayInlay_%02d" % index,
		Vector3(0.08, 0.008, 1.18),
		Vector3(D.DORM_INNER_X + 0.05, 0.004, center_z),
		Color("#d4c6b0"),
		false,
		0.0,
		0.34
	)


func _build_rooms(parent: Node3D, room_count: int, themes: Array[Color]) -> void:
	for index in range(room_count):
		var activity := ACTIVITY_ROOM_SCENE.instantiate() as ModularActivityRoom
		activity.auto_preview = false
		activity.name = "ActivityRoom_%02d" % (index + 1)
		activity.position = Vector3(D.ACTIVITY_CENTER_X, 0.0, D.cell_center_z(index))
		parent.add_child(activity)
		activity.build(themes[index], index)

		var dorm := DORM_ROOM_SCENE.instantiate() as ModularDormRoom
		dorm.auto_preview = false
		dorm.name = "DormRoom_%02d" % (index + 1)
		dorm.position = Vector3(D.DORM_CENTER_X, 0.0, D.cell_center_z(index))
		parent.add_child(dorm)
		dorm.build(index, clampi(bed_count - index * 4, 0, 4))


func _build_activity_boundaries(parent: Node3D, room_count: int, themes: Array[Color]) -> void:
	_add_activity_partition(parent, "ActivityStartWall", 0.0, themes[0], D.EXTERIOR_COLOR)
	for boundary_index in range(1, room_count):
		if _activity_group(boundary_index - 1) == _activity_group(boundary_index):
			continue
		_add_activity_partition(
			parent,
			"ActivityPartition_%02d" % boundary_index,
			-float(boundary_index) * D.CELL_PITCH,
			themes[boundary_index],
			themes[boundary_index - 1]
		)
	_add_activity_partition(
		parent,
		"ActivityEndWall",
		-float(room_count) * D.CELL_PITCH,
		D.EXTERIOR_COLOR,
		themes[room_count - 1]
	)


func _add_activity_partition(parent: Node3D, wall_name: String, z_position: float, negative_color: Color, positive_color: Color) -> void:
	G.add_wall(
		parent,
		wall_name,
		Vector3(D.ACTIVITY_DEPTH, D.WALL_HEIGHT, D.WALL_THICKNESS),
		Vector3(D.ACTIVITY_CENTER_X, D.WALL_HEIGHT / 2.0, z_position),
		negative_color,
		positive_color
	)


func _build_dorm_boundaries(parent: Node3D, room_count: int) -> void:
	for boundary_index in range(room_count + 1):
		var negative_color := D.DORM_WALL_COLOR if boundary_index < room_count else D.EXTERIOR_COLOR
		var positive_color := D.DORM_WALL_COLOR if boundary_index > 0 else D.EXTERIOR_COLOR
		G.add_wall(
			parent,
			"DormPartition_%02d" % boundary_index,
			Vector3(D.DORM_DEPTH, D.WALL_HEIGHT, D.WALL_THICKNESS),
			Vector3(D.DORM_CENTER_X, D.WALL_HEIGHT / 2.0, -float(boundary_index) * D.CELL_PITCH),
			negative_color,
			positive_color
		)


func _build_end_wall(parent: Node3D, room_count: int) -> void:
	var end_z := -float(room_count) * D.CELL_PITCH
	G.add_wall(
		parent,
		"CorridorEndWall",
		Vector3(D.CORRIDOR_WIDTH, D.WALL_HEIGHT, D.WALL_THICKNESS),
		Vector3(0.0, D.WALL_HEIGHT / 2.0, end_z),
		D.EXTERIOR_COLOR,
		D.CORRIDOR_WALL_COLOR
	)
	G.add_box(parent, "MuralFrame", Vector3(2.72, 1.92, 0.055), Vector3(0.0, 1.52, end_z + 0.09), Color("#172129"))
	var mural := MeshInstance3D.new()
	mural.name = "EndWallMural"
	var quad := QuadMesh.new()
	quad.size = Vector2(2.48, 1.68)
	mural.mesh = quad
	mural.position = Vector3(0.0, 1.52, end_z + 0.122)
	var mural_material := StandardMaterial3D.new()
	mural_material.albedo_texture = MURAL_TEXTURE
	mural_material.roughness = 0.62
	mural_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	mural.material_override = mural_material
	parent.add_child(mural)
	G.add_box(parent, "MuralLight", Vector3(1.8, 0.045, 0.045), Vector3(0.0, 2.62, end_z + 0.16), Color("#f2d29b"), false, 1.5)


func _build_portal_room(parent: Node3D) -> void:
	var portal_room := PORTAL_ROOM_SCENE.instantiate() as ModularPortalRoom
	portal_room.auto_preview = false
	portal_room.name = "PortalRoom"
	parent.add_child(portal_room)
	portal_room.build()


func _activity_group(index: int) -> int:
	if index < activity_group_ids.size():
		return activity_group_ids[index]
	return index + 1000


func _themes_for_rooms(room_count: int) -> Array[Color]:
	var result: Array[Color] = []
	for index in range(room_count):
		result.append(THEMES[index % THEMES.size()])
	return result


func _update_camera(room_count: int) -> void:
	var camera := get_node_or_null("Camera3D") as Camera3D
	if camera == null:
		return
	var building_length := float(room_count) * D.CELL_PITCH
	_camera_default_target = Vector3(0.35, 0.55, (-building_length + 3.0) / 2.0)
	_camera_default_size = clampf(
		maxf(22.0, building_length + 4.0),
		CAMERA_MIN_SIZE,
		CAMERA_MAX_SIZE
	)
	var half_width := maxf(
		absf(D.ACTIVITY_OUTER_X - _camera_default_target.x),
		absf(D.DORM_OUTER_X - _camera_default_target.x)
	)
	var half_length := maxf(
		absf(_camera_default_target.z),
		absf(-building_length - _camera_default_target.z)
	)
	var half_height := maxf(
		_camera_default_target.y,
		D.WALL_HEIGHT - _camera_default_target.y
	)
	var building_radius := Vector3(half_width, half_height, half_length).length()
	_camera_default_distance = maxf(
		CAMERA_START_OFFSET.length(),
		building_radius + CAMERA_BOUNDS_MARGIN
	)
	_reset_camera()


func _reset_camera() -> void:
	var camera := get_node_or_null("Camera3D") as Camera3D
	if camera == null:
		return
	_camera_target = _camera_default_target
	_camera_distance = _camera_default_distance
	_camera_yaw = atan2(CAMERA_START_OFFSET.x, CAMERA_START_OFFSET.z)
	_camera_pitch = asin(CAMERA_START_OFFSET.y / _camera_distance)
	camera.size = _camera_default_size
	_apply_camera_transform(camera)


func _apply_camera_transform(camera: Camera3D) -> void:
	var horizontal_scale := cos(_camera_pitch) * _camera_distance
	var offset := Vector3(
		sin(_camera_yaw) * horizontal_scale,
		sin(_camera_pitch) * _camera_distance,
		cos(_camera_yaw) * horizontal_scale
	)
	camera.position = _camera_target + offset
	camera.look_at(to_global(_camera_target), global_transform.basis.y.normalized())
