@tool
class_name ModularPortalRoom
extends Node3D

const D := preload("res://rooms/room_dimensions.gd")
const G := preload("res://rooms/room_geometry.gd")
const TELEPORTER_SCENE := preload("res://rooms/assets/teleporter/teleporter.tscn")
const ROOM_SIZE: float = 3.0
const DOOR_WIDTH: float = 1.4
const DOOR_HEIGHT: float = 2.2
const TELEPORTER_SCALE: float = 0.5
const TELEPORTER_COLOR := Color("#42e8e0")
const ROOM_COLOR := Color("#cbdad5")
const FLOOR_COLOR := Color("#b9c8c4")
const TELEPORTER_RING_CENTER_Z: float = 1.84
const TELEPORTER_RING_RADIUS: float = 1.05
const TELEPORTER_RUNWAY_WIDTH: float = 0.82
const TELEPORTER_RUNWAY_LENGTH: float = 1.0

@export var auto_preview: bool = true

var _generated: Node3D


func _ready() -> void:
	if auto_preview:
		build()


func build() -> void:
	_generated = _replace_generated()
	G.add_floor(_generated, "PortalFloor", ROOM_SIZE, ROOM_SIZE, Vector3(0.0, 0.0, ROOM_SIZE / 2.0), FLOOR_COLOR)
	for x_position in [-ROOM_SIZE / 2.0, ROOM_SIZE / 2.0]:
		G.add_wall(
			_generated,
			"PortalSideWall",
			Vector3(D.WALL_THICKNESS, D.WALL_HEIGHT, ROOM_SIZE),
			Vector3(x_position, D.WALL_HEIGHT / 2.0, ROOM_SIZE / 2.0),
			ROOM_COLOR,
			ROOM_COLOR
		)
	G.add_wall(
		_generated,
		"PortalFarWall",
		Vector3(ROOM_SIZE, D.WALL_HEIGHT, D.WALL_THICKNESS),
		Vector3(0.0, D.WALL_HEIGHT / 2.0, ROOM_SIZE),
		ROOM_COLOR,
		ROOM_COLOR
	)
	_build_corridor_door()
	_build_teleporter()
	_build_animation_hooks()
	var camera_anchor := Marker3D.new()
	camera_anchor.name = "CameraAnchor"
	camera_anchor.position = Vector3(0.0, 6.5, ROOM_SIZE / 2.0)
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


func _build_corridor_door() -> void:
	var side_width := (ROOM_SIZE - DOOR_WIDTH) / 2.0
	var side_offset := DOOR_WIDTH / 2.0 + side_width / 2.0
	for offset in [-side_offset, side_offset]:
		G.add_wall(
			_generated,
			"CorridorDoorSide",
			Vector3(side_width, D.WALL_HEIGHT, D.WALL_THICKNESS),
			Vector3(offset, D.WALL_HEIGHT / 2.0, 0.0),
			D.CORRIDOR_WALL_COLOR,
			ROOM_COLOR
		)
	var lintel_height := D.WALL_HEIGHT - DOOR_HEIGHT
	G.add_wall(
		_generated,
		"CorridorDoorLintel",
		Vector3(DOOR_WIDTH, lintel_height, D.WALL_THICKNESS),
		Vector3(0.0, DOOR_HEIGHT + lintel_height / 2.0, 0.0),
		D.CORRIDOR_WALL_COLOR,
		ROOM_COLOR
	)
	for x_position in [-DOOR_WIDTH / 2.0, DOOR_WIDTH / 2.0]:
		G.add_box(_generated, "DoorLightStrip", Vector3(0.055, DOOR_HEIGHT, 0.07), Vector3(x_position, DOOR_HEIGHT / 2.0, -0.07), TELEPORTER_COLOR, false, 2.4)
	G.add_box(_generated, "DoorLightHeader", Vector3(DOOR_WIDTH + 0.06, 0.055, 0.07), Vector3(0.0, DOOR_HEIGHT, -0.07), TELEPORTER_COLOR, false, 2.4)
	G.add_box(_generated, "DoorLeafLeft", Vector3(0.16, DOOR_HEIGHT - 0.08, 0.065), Vector3(-DOOR_WIDTH / 2.0 + 0.08, (DOOR_HEIGHT - 0.08) / 2.0, 0.0), Color("#d7cbb8"))
	G.add_box(_generated, "DoorLeafRight", Vector3(0.16, DOOR_HEIGHT - 0.08, 0.065), Vector3(DOOR_WIDTH / 2.0 - 0.08, (DOOR_HEIGHT - 0.08) / 2.0, 0.0), Color("#d7cbb8"))


func _build_teleporter() -> void:
	var stage_center := Vector3(0.0, 0.0, TELEPORTER_RING_CENTER_Z)
	G.add_cylinder(
		_generated,
		"TeleporterRingUnderlight",
		TELEPORTER_RING_RADIUS,
		0.022,
		stage_center + Vector3(0.0, 0.025, 0.0),
		TELEPORTER_COLOR,
		2.0
	)
	G.add_box(
		_generated,
		"TeleporterRunwayUnderlight",
		Vector3(TELEPORTER_RUNWAY_WIDTH, 0.024, TELEPORTER_RUNWAY_LENGTH),
		Vector3(0.0, 0.027, stage_center.z - 1.15),
		TELEPORTER_COLOR,
		false,
		1.65,
		0.42
	)
	var teleporter := TELEPORTER_SCENE.instantiate() as Node3D
	teleporter.name = "Teleporter"
	teleporter.scale = Vector3.ONE * TELEPORTER_SCALE
	teleporter.position = stage_center + Vector3(0.0, 0.04, 0.0)
	_generated.add_child(teleporter)
	G.add_visual_bounds_collision(_generated, "TeleporterFixture", teleporter)
	var light := OmniLight3D.new()
	light.name = "TeleporterLight"
	light.position = stage_center + Vector3(0.0, 1.15, 0.0)
	light.light_color = TELEPORTER_COLOR
	light.light_energy = 2.1
	light.omni_range = 3.6
	light.shadow_enabled = false
	_generated.add_child(light)


func _build_animation_hooks() -> void:
	var trigger := Area3D.new()
	trigger.name = "CorridorDoorTrigger"
	trigger.position = Vector3(0.0, 1.1, -0.35)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(DOOR_WIDTH + 0.8, 2.2, 1.0)
	collision.shape = shape
	trigger.add_child(collision)
	_generated.add_child(trigger)
	var animation_player := AnimationPlayer.new()
	animation_player.name = "CorridorDoorAnimation"
	_generated.add_child(animation_player)
