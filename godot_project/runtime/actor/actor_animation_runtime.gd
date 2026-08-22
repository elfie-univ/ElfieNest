class_name ActorAnimationRuntime
extends RefCounted

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
const PREVIEW_POSES := {
	"pose_thinking": "res://characters/animation/pose_thinking.fbx",
	"pose_waving": "res://characters/animation/pose_waving.fbx",
	"pose_victory": "res://characters/animation/pose_victory.fbx",
	"pose_thumbs_up": "res://characters/animation/pose_thumbs_up.fbx",
	"pose_hands_on_hips": "res://characters/animation/pose_hands_on_hips.fbx",
}
const PREVIEW_POSE_FRAME_RATIOS := {
	"pose_thinking": 0.60,
	"pose_waving": 0.60,
	"pose_victory": 0.52,
	"pose_thumbs_up": 0.52,
	"pose_hands_on_hips": 0.0,
}
const LOOPING_ANIMATIONS := {"idle": true, "walking": true, "running": true}

var _actor: CharacterBody3D
var _visual_root: Node3D
var _animation_player: AnimationPlayer
var _preview_tween: Tween


func setup(
	actor: CharacterBody3D,
	visual_root: Node3D,
	animation_player: AnimationPlayer,
	install_shared: bool,
	install_preview_poses: bool = false,
) -> void:
	_actor = actor
	_visual_root = visual_root
	_animation_player = animation_player
	var animation_sources := {}
	if install_shared:
		animation_sources.merge(SHARED_ANIMATIONS)
	if install_preview_poses:
		animation_sources.merge(PREVIEW_POSES)
	_install_animations(animation_sources)


func play(animation_name: String) -> void:
	if not _animation_player.has_animation(animation_name):
		return
	if _animation_player.current_animation != animation_name:
		_animation_player.play(animation_name)


func play_expression(expression: String) -> bool:
	var animation_name := expression
	if expression == "happy":
		animation_name = "twist_dance"
	elif expression == "excited":
		animation_name = "jump"
	if not SHARED_ANIMATIONS.has(animation_name):
		return false
	_actor.set_meta("runtime_expression", expression)
	play(animation_name)
	return true


func play_speech() -> void:
	_actor.set_meta("speaking", true)
	play("idle")
	_actor.get_tree().create_timer(0.35).timeout.connect(
		func() -> void: _actor.set_meta("speaking", false),
		CONNECT_ONE_SHOT,
	)


func play_preview_intent(intent: Dictionary) -> bool:
	if String(intent.get("type", "")) != "motion":
		return false
	var motion := String(intent.get("motion", ""))
	if motion == "pose_default":
		reset_preview_pose()
		return true
	if PREVIEW_POSE_FRAME_RATIOS.has(motion):
		return _play_frozen_pose(motion)
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


func _install_animations(animation_sources: Dictionary) -> void:
	if animation_sources.is_empty():
		return
	if _animation_player.has_animation_library(""):
		_animation_player.remove_animation_library("")
	var merged_library := AnimationLibrary.new()
	for animation_name: String in animation_sources:
		var library := load(animation_sources[animation_name]) as AnimationLibrary
		if library == null or library.get_animation_list().is_empty():
			push_warning("无法加载角色动画：%s" % animation_sources[animation_name])
			continue
		var source_name := _select_source_animation(library, animation_name)
		var animation := library.get_animation(source_name).duplicate(true) as Animation
		if LOOPING_ANIMATIONS.has(animation_name):
			animation.loop_mode = Animation.LOOP_LINEAR
		merged_library.add_animation(animation_name, animation)
	_animation_player.add_animation_library("", merged_library)


func reset_preview_pose() -> void:
	if _preview_tween != null and _preview_tween.is_valid():
		_preview_tween.kill()
	var pose_scales: Array[Array] = []
	for node in _visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		var skeleton_scales: Array[Vector3] = []
		for bone_index in range(skeleton.get_bone_count()):
			skeleton_scales.append(skeleton.get_bone_pose_scale(bone_index))
		pose_scales.append(skeleton_scales)
	_animation_player.stop()
	_animation_player.playback_active = false
	var skeleton_index := 0
	for node in _visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		skeleton.reset_bone_poses()
		var skeleton_scales := pose_scales[skeleton_index] as Array
		for bone_index in range(skeleton_scales.size()):
			skeleton.set_bone_pose_scale(bone_index, skeleton_scales[bone_index] as Vector3)
		skeleton_index += 1


func _play_frozen_pose(animation_name: String) -> bool:
	if not _animation_player.has_animation(animation_name):
		return false
	var animation := _animation_player.get_animation(animation_name)
	if animation == null:
		return false
	_animation_player.playback_active = true
	_animation_player.play(animation_name)
	_animation_player.seek(
		animation.length * clampf(float(PREVIEW_POSE_FRAME_RATIOS[animation_name]), 0.0, 1.0),
		true,
	)
	_animation_player.playback_active = false
	return true


func _select_source_animation(library: AnimationLibrary, preferred_name: String) -> String:
	if library.has_animation(preferred_name):
		return preferred_name
	return String(library.get_animation_list()[0])


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
	_preview_tween = _actor.create_tween()
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
