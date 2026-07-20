class_name ElfieActor
extends CharacterBody3D

const WALK_SPEED := 1.15
const ARRIVAL_DISTANCE := 0.22
const WANDER_RADIUS_X := 1.7
const WANDER_MIN_Z := -30.0
const WANDER_MAX_Z := -2.0
const BASE_COLLISION_RADIUS := 0.34
const BASE_COLLISION_HEIGHT := 1.72
const SHARED_ANIMATIONS := {
	"idle": "res://characters/animation/idle.fbx",
	"walking": "res://characters/animation/walking.fbx",
	"running": "res://characters/animation/running.fbx",
	"jump": "res://characters/animation/jump.fbx",
	"twist_dance": "res://characters/animation/Twist Dance.fbx",
	"left_strafe": "res://characters/animation/left strafe.fbx",
	"left_strafe_walking": "res://characters/animation/left strafe walking.fbx",
	"left_turn": "res://characters/animation/left turn.fbx",
	"left_turn_90": "res://characters/animation/left turn 90.fbx",
	"right_strafe": "res://characters/animation/right strafe.fbx",
	"right_strafe_walking": "res://characters/animation/right strafe walking.fbx",
	"right_turn": "res://characters/animation/right turn.fbx",
	"right_turn_90": "res://characters/animation/right turn 90.fbx",
}
const LOOPING_ANIMATIONS := {"idle": true, "walking": true, "running": true}

@export var species_id := ""
@export var install_shared_animations := true

var elfie_id := ""
var _target_position: Vector3
var _has_target := false
var _wander_clock := 0.0
var _wander_seed := 0

@onready var _visual_root: Node3D = $VisualRoot
@onready var _collision_shape: CollisionShape3D = $CollisionShape3D
@onready var _animation_player: AnimationPlayer = $AnimationPlayer


func _ready() -> void:
	if install_shared_animations:
		_install_shared_animations()


func configure(
	identity: String,
	spawn_position: Vector3,
	appearance: Dictionary = {},
) -> void:
	elfie_id = identity
	global_position = spawn_position
	_wander_seed = abs(elfie_id.hash())
	_wander_clock = float(_wander_seed % 500) / 100.0
	_apply_appearance(appearance)
	_play_animation("idle")
	_pick_wander_target()


func set_target_name(target_name: String) -> void:
	var target_hash: int = absi(target_name.hash())
	_target_position = Vector3(
		-WANDER_RADIUS_X + float(target_hash % 340) / 100.0,
		0.0,
		WANDER_MIN_Z + float((target_hash / 100) % 2600) / 100.0
	)
	_has_target = true


func _physics_process(delta: float) -> void:
	if not _has_target:
		_wander_clock += delta
		if _wander_clock >= 5.0:
			_pick_wander_target()
	if not _has_target:
		velocity = Vector3.ZERO
		_play_animation("idle")
		return

	var offset := _target_position - global_position
	offset.y = 0.0
	if offset.length() <= ARRIVAL_DISTANCE:
		_has_target = false
		velocity = Vector3.ZERO
		_play_animation("idle")
		return

	var direction := offset.normalized()
	velocity = direction * WALK_SPEED
	_play_animation("walking")
	look_at(global_position + direction, Vector3.UP)
	move_and_slide()


func _install_shared_animations() -> void:
	if _animation_player.has_animation_library(""):
		_animation_player.remove_animation_library("")
	var merged_library := AnimationLibrary.new()
	for animation_name: String in SHARED_ANIMATIONS:
		var library := load(SHARED_ANIMATIONS[animation_name]) as AnimationLibrary
		if library == null or library.get_animation_list().is_empty():
			push_warning("无法加载公共角色动画：%s" % SHARED_ANIMATIONS[animation_name])
			continue
		var source_name := _select_source_animation(library, animation_name)
		var animation := library.get_animation(source_name).duplicate(true) as Animation
		if LOOPING_ANIMATIONS.has(animation_name):
			animation.loop_mode = Animation.LOOP_LINEAR
		merged_library.add_animation(animation_name, animation)
	_animation_player.add_animation_library("", merged_library)


func _select_source_animation(library: AnimationLibrary, preferred_name: String) -> String:
	if library.has_animation(preferred_name):
		return preferred_name
	return String(library.get_animation_list()[0])


func _apply_appearance(appearance: Dictionary) -> void:
	var height_scale := _appearance_scale(
		appearance.get("height_scale", appearance.get("height", "standard")),
		{"short": 0.92, "standard": 1.0, "tall": 1.08},
	)
	var build_scale := _appearance_scale(
		appearance.get("build_scale", appearance.get("build", "standard")),
		{"slim": 0.92, "standard": 1.0, "plump": 1.08},
	)
	height_scale = clampf(height_scale, 0.85, 1.15)
	build_scale = clampf(build_scale, 0.85, 1.15)
	_visual_root.scale = Vector3(build_scale, height_scale, build_scale)

	var capsule := _collision_shape.shape.duplicate() as CapsuleShape3D
	capsule.radius = BASE_COLLISION_RADIUS * build_scale
	capsule.height = maxf(
		BASE_COLLISION_HEIGHT * height_scale,
		capsule.radius * 2.0,
	)
	_collision_shape.shape = capsule
	_collision_shape.position.y = capsule.height * 0.5
	_apply_blend_shapes(appearance.get("blend_shapes", {}))


func _apply_blend_shapes(raw_values: Variant) -> void:
	if not raw_values is Dictionary:
		return
	for node in _visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for shape_name: Variant in (raw_values as Dictionary):
			if mesh_instance.find_blend_shape_by_name(StringName(shape_name)) < 0:
				continue
			mesh_instance.set(
				"blend_shapes/%s" % String(shape_name),
				clampf(float((raw_values as Dictionary)[shape_name]), 0.0, 1.0),
			)


func _appearance_scale(value: Variant, named_values: Dictionary) -> float:
	if value is float or value is int:
		return float(value)
	return float(named_values.get(String(value), 1.0))


func visual_bounds() -> AABB:
	var bounds := AABB()
	var has_bounds := false
	for node in _visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		for bone_index in range(skeleton.get_bone_count()):
			var point := skeleton.to_global(
				skeleton.get_bone_global_pose(bone_index).origin
			)
			if has_bounds:
				bounds = bounds.expand(point)
			else:
				bounds = AABB(point, Vector3.ZERO)
				has_bounds = true
	if has_bounds:
		return bounds.grow(0.14)
	return bounds


func _play_animation(animation_name: String) -> void:
	if not _animation_player.has_animation(animation_name):
		return
	if _animation_player.current_animation != animation_name:
		_animation_player.play(animation_name)


func _pick_wander_target() -> void:
	_wander_seed = int(fposmod(float(_wander_seed * 1103515245 + 12345), 2147483647.0))
	var x_value := float(_wander_seed % 340) / 100.0 - WANDER_RADIUS_X
	_wander_seed = int(fposmod(float(_wander_seed * 1103515245 + 12345), 2147483647.0))
	var z_value := WANDER_MIN_Z + float(_wander_seed % 2600) / 100.0
	_target_position = Vector3(x_value, 0.0, z_value)
	_has_target = true
	_wander_clock = 0.0
