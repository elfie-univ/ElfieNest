class_name ElfieActor
extends CharacterBody3D

const WALK_SPEED := 1.15
const ARRIVAL_DISTANCE := 0.22
const WANDER_RADIUS_X := 1.7
const WANDER_MIN_Z := -30.0
const WANDER_MAX_Z := -2.0
const BASE_COLLISION_RADIUS := 0.34
const BASE_COLLISION_HEIGHT := 1.72
const BONE_SCALE_CONTROLS := {
	"HeadScale": {
		"mode": "uniform",
		"bones": ["mixamorig_Head"],
	},
	"NeckLength": {
		"mode": "length",
		"bones": ["mixamorig_Neck"],
	},
	"ArmLength": {
		"mode": "length",
		"bones": [
			"mixamorig_LeftArm",
			"mixamorig_LeftForeArm",
			"mixamorig_RightArm",
			"mixamorig_RightForeArm",
		],
	},
	"LegLength": {
		"mode": "length",
		"bones": [
			"mixamorig_LeftUpLeg",
			"mixamorig_LeftLeg",
			"mixamorig_RightUpLeg",
			"mixamorig_RightLeg",
		],
	},
	"HandScale": {
		"mode": "uniform",
		"bones": ["mixamorig_LeftHand", "mixamorig_RightHand"],
	},
	"PawScale": {
		"mode": "uniform",
		"bones": ["mixamorig_LeftFoot", "mixamorig_RightFoot"],
	},
	"TailLength": {
		"mode": "length",
		"bones": ["mixamorig_Tail_Bone"],
	},
}
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
var _preview_tween: Tween

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


func prepare_preview() -> void:
	install_shared_animations = false


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
	_apply_bone_scales(appearance.get("bone_scales", {}))
	_apply_blend_shapes(appearance.get("blend_shapes", {}))


func _apply_bone_scales(raw_values: Variant) -> void:
	if not raw_values is Dictionary:
		return
	for node in _visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		for control_name: String in BONE_SCALE_CONTROLS:
			if control_name == "HeadScale" or control_name == "NeckLength":
				continue
			var control: Dictionary = BONE_SCALE_CONTROLS[control_name]
			var factor := clampf(
				float((raw_values as Dictionary).get(control_name, 1.0)),
				0.5,
				1.5,
			)
			var pose_scale := (
				Vector3.ONE * factor
				if control["mode"] == "uniform"
				else Vector3(1.0, factor, 1.0)
			)
			for bone_name: String in control["bones"]:
				var bone_index := skeleton.find_bone(bone_name)
				if bone_index >= 0:
					skeleton.set_bone_pose_scale(bone_index, pose_scale)
		_apply_neck_and_head_scales(skeleton, raw_values as Dictionary)


func _apply_neck_and_head_scales(
	skeleton: Skeleton3D,
	raw_values: Dictionary,
) -> void:
	var neck_factor := clampf(float(raw_values.get("NeckLength", 1.0)), 0.5, 1.5)
	var head_factor := clampf(float(raw_values.get("HeadScale", 1.0)), 0.5, 1.5)
	var neck_index := skeleton.find_bone("mixamorig_Neck")
	if neck_index >= 0:
		skeleton.set_bone_pose_scale(neck_index, Vector3(1.0, neck_factor, 1.0))
	var head_index := skeleton.find_bone("mixamorig_Head")
	if head_index >= 0:
		# Neck scale is inherited by Head; cancel it on the local length axis.
		skeleton.set_bone_pose_scale(
			head_index,
			Vector3(head_factor, head_factor / neck_factor, head_factor),
		)


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


func preview_focus_point(target: String) -> Vector3:
	var bounds := visual_bounds()
	if bounds.size.is_zero_approx():
		return global_position + Vector3(0.0, 0.9, 0.0)
	if target == "head":
		return Vector3(
			bounds.get_center().x,
			bounds.end.y - bounds.size.y * 0.12,
			bounds.get_center().z,
		)
	return bounds.get_center()


func play_preview_intent(intent: Dictionary) -> bool:
	if String(intent.get("type", "")) != "motion":
		return false
	var motion := String(intent.get("motion", ""))
	match motion:
		"nod_head":
			_animate_head_gesture.call_deferred(Vector3.RIGHT, [-0.22, 0.12, 0.0])
			return true
		"shake_head":
			_animate_head_gesture.call_deferred(Vector3.UP, [-0.24, 0.24, 0.0])
			return true
		_:
			if not SHARED_ANIMATIONS.has(motion) or not _animation_player.has_animation(motion):
				return false
			_animation_player.play(motion)
			return true


func _animate_head_gesture(axis: Vector3, angles: Array) -> void:
	var skeleton := _find_preview_skeleton()
	if skeleton == null:
		return
	var head_index := skeleton.find_bone("mixamorig_Head")
	if head_index < 0:
		return
	if _preview_tween != null and _preview_tween.is_valid():
		_preview_tween.kill()
	var base_rotation := skeleton.get_bone_pose_rotation(head_index)
	_preview_tween = create_tween()
	var previous := 0.0
	for target: float in angles:
		_preview_tween.tween_method(
			_set_preview_head_angle.bind(skeleton, head_index, base_rotation, axis),
			previous,
			target,
			0.12,
		)
		previous = target


func _set_preview_head_angle(
	angle: float,
	skeleton: Skeleton3D,
	head_index: int,
	base_rotation: Quaternion,
	axis: Vector3,
) -> void:
	skeleton.set_bone_pose_rotation(
		head_index,
		base_rotation * Quaternion(axis, angle),
	)


func _find_preview_skeleton() -> Skeleton3D:
	for node in _visual_root.find_children("*", "Skeleton3D", true, false):
		return node as Skeleton3D
	return null


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
