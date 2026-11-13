class_name ActorAnimationRuntime
extends RefCounted

const SHARED_ANIMATIONS := {
	"idle": "res://characters/animation/idle.fbx",
	"walking": "res://characters/animation/walking.fbx",
	"running": "res://characters/animation/running.fbx",
	"jump": "res://characters/animation/jump.fbx",
	"twist_dance": "res://characters/animation/Twist Dance.fbx",
	"pose_waving": "res://characters/animation/pose_waving.fbx",
	"pose_thinking": "res://characters/animation/pose_thinking.fbx",
	"pose_victory": "res://characters/animation/pose_victory.fbx",
	"pose_thumbs_up": "res://characters/animation/pose_thumbs_up.fbx",
	"pose_hands_on_hips": "res://characters/animation/pose_hands_on_hips.fbx",
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
const CLIP_BLEND_SECONDS := 0.22
const POSTURE_BLEND_SECONDS := 0.65
const TURN_RESPONSE := 12.0
const HEAD_GESTURES := {
	"nod_head": {"axis": Vector3.RIGHT, "angles": [-0.22, 0.12, 0.0]},
	"shake_head": {"axis": Vector3.UP, "angles": [-0.24, 0.24, 0.0]},
}
const HEAD_KEY_SECONDS := 0.12
const EYELIDS := preload("res://runtime/actor/actor_eyelids.gd")
const FOOT_CONTACT := preload("res://runtime/actor/furniture_contact.gd")

var _actor: CharacterBody3D
var _visual_root: Node3D
var _animation_player: AnimationPlayer
var _preview_tween: Tween
var _expression_animation := ""
var _posture := ""
var _posture_target: Array[Dictionary] = []
var _transition_source: Array[Dictionary] = []
var _transition_visual_from := Transform3D.IDENTITY
var _transition_visual_to := Transform3D.IDENTITY
var _transition_elapsed := POSTURE_BLEND_SECONDS
var _breath_phase := 0.0
var _heading_target := Quaternion.IDENTITY
var _head_gesture: Dictionary = {}
var _eyelids := EYELIDS.new()
var _frozen_floor_active := false
var _frozen_floor_sampled := false
var _frozen_floor_offset := Vector3.ZERO


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
	_heading_target = visual_root.quaternion
	# Runtime samples the clip before applying visual overlays. Preview keeps its
	# existing frozen-pose/tween clock and never uses advance().
	if not install_preview_poses:
		_animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	_animation_player.animation_finished.connect(_on_animation_finished)
	var animation_sources := {}
	if install_shared:
		animation_sources.merge(SHARED_ANIMATIONS)
	if install_preview_poses:
		animation_sources.merge(PREVIEW_POSES)
	_install_animations(animation_sources)
	_eyelids.bind(visual_root)


func play(animation_name: String) -> void:
	if not _animation_player.has_animation(animation_name):
		return
	if not _expression_animation.is_empty():
		if animation_name == "idle":
			return
		if animation_name != _expression_animation:
			cancel_expression()
	_animation_player.playback_active = true
	if _animation_player.current_animation != animation_name:
		_animation_player.play(animation_name, CLIP_BLEND_SECONDS)


func cancel_expression() -> void:
	_clear_frozen_floor()
	_eyelids.reset()
	_restore_head_base()
	_head_gesture.clear()
	_expression_animation = ""
	_actor.remove_meta("runtime_expression")


func _on_animation_finished(animation_name: StringName) -> void:
	if String(animation_name) == _expression_animation:
		cancel_expression()
		play("idle")


func capture_visual_pose() -> Dictionary:
	var bones: Array[Dictionary] = []
	for node in _visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		for bone in range(skeleton.get_bone_count()):
			bones.append({
				"skeleton": skeleton, "bone": bone,
				"rotation": skeleton.get_bone_pose_rotation(bone),
				"position": skeleton.get_bone_pose_position(bone),
			})
	return {"visual": _visual_root.global_transform, "bones": bones}


func standing_visual_transform() -> Transform3D:
	var result := _visual_root.transform
	result.origin -= _frozen_floor_offset
	if _posture.is_empty() and _transition_elapsed < POSTURE_BLEND_SECONDS:
		result = _transition_visual_to
	result.basis = Basis(_heading_target).scaled(result.basis.get_scale())
	return result


func transition_from(source: Dictionary, posture: String = "") -> void:
	# The caller has already resolved the physical contact/exit. Interpolate only
	# its visual child and bone poses, including when an earlier blend is interrupted.
	_clear_frozen_floor()
	if posture != "sleeping":
		_eyelids.reset()
	_posture = posture
	_breath_phase = 0.0
	_posture_target.assign(capture_visual_pose()["bones"])
	_transition_source.assign(source["bones"])
	_transition_visual_to = _visual_root.transform
	_transition_visual_from = _actor.global_transform.affine_inverse() * (source["visual"] as Transform3D)
	_transition_elapsed = 0.0
	_heading_target = _transition_visual_to.basis.orthonormalized().get_rotation_quaternion()
	_visual_root.transform = _transition_visual_from
	_apply_bone_blend(_posture_target, 0.0)


func reset_procedural_pose() -> void:
	_clear_frozen_floor()
	_eyelids.reset()
	# Remove the last breathing sample before the caller samples an exit clip.
	for pose: Dictionary in _posture_target:
		var skeleton := pose["skeleton"] as Skeleton3D
		skeleton.set_bone_pose_rotation(int(pose["bone"]), pose["rotation"] as Quaternion)
		skeleton.set_bone_pose_position(int(pose["bone"]), pose["position"] as Vector3)
	_posture = ""
	_posture_target.clear()
	_transition_source.clear()
	_transition_elapsed = POSTURE_BLEND_SECONDS


func begin_sleep_eyes(owner: Node) -> void:
	_eyelids.acquire(owner)


func sample_sleep_eyes(owner: Node, amount: float) -> void:
	_eyelids.sample(owner, amount)


func end_sleep_eyes(owner: Node) -> void:
	_eyelids.release(owner)


func smooth_heading(previous_global_basis: Basis) -> void:
	if _posture.is_empty() and _transition_elapsed >= POSTURE_BLEND_SECONDS:
		_visual_root.global_basis = previous_global_basis


func advance(delta: float) -> void:
	_restore_head_base()
	if _frozen_floor_active and _transition_elapsed < POSTURE_BLEND_SECONDS:
		# The blend replaces the visual transform; sample its changing feet only
		# during that transition, then retain the final offset for the held pose.
		_remove_frozen_floor_offset()
	var step := maxf(delta, 0.0)
	if _posture.is_empty():
		if _transition_elapsed < POSTURE_BLEND_SECONDS:
			# Untracked bones must start from the exit pose, not the preceding
			# interpolated frame, or an interrupted posture would accumulate drift.
			_apply_bone_blend(_posture_target, 1.0)
		# Manual advance ignores playback_active; preserve the sampled frozen pose
		# until play() explicitly resumes playback for a replacement or exit.
		if _animation_player.playback_active:
			_animation_player.advance(step)
	var blending := _transition_elapsed < POSTURE_BLEND_SECONDS
	var weight := 1.0
	if blending:
		_transition_elapsed = minf(_transition_elapsed + step, POSTURE_BLEND_SECONDS)
		weight = smoothstep(0.0, POSTURE_BLEND_SECONDS, _transition_elapsed)
		_visual_root.transform = _transition_visual_from.interpolate_with(_transition_visual_to, weight)
	if not _posture.is_empty():
		_apply_bone_blend(_posture_target, weight)
		_breath_phase = fmod(_breath_phase + step * TAU / 4.2, TAU)
		_apply_breathing(weight)
	elif blending:
		var live_pose := capture_visual_pose()
		_apply_bone_blend(live_pose["bones"], weight)
	else:
		_visual_root.quaternion = _visual_root.quaternion.slerp(
			_heading_target, 1.0 - exp(-TURN_RESPONSE * step),
		)
	if _transition_elapsed >= POSTURE_BLEND_SECONDS:
		_transition_source.clear()
	_advance_head_gesture(step)
	_apply_frozen_floor()


func _remove_frozen_floor_offset() -> void:
	_visual_root.position -= _frozen_floor_offset
	_frozen_floor_offset = Vector3.ZERO
	_frozen_floor_sampled = false


func _clear_frozen_floor() -> void:
	_remove_frozen_floor_offset()
	_frozen_floor_active = false


func _apply_frozen_floor() -> void:
	if not _frozen_floor_active or _frozen_floor_sampled:
		return
	var sole := FOOT_CONTACT.sole_y(_actor as ElfieActor)
	if not is_finite(sole):
		return
	# Actor origin is the standing contact plane. Move only the visual child;
	# keep every authored bone pose and the collision/navigation body intact.
	var before := _visual_root.position
	_visual_root.global_position.y += _actor.global_position.y - sole
	_frozen_floor_offset = _visual_root.position - before
	_frozen_floor_sampled = true


func supports_head_gestures() -> bool:
	var skeleton := _find_preview_skeleton()
	return skeleton != null and _head_bone(skeleton) >= 0


func _head_bone(skeleton: Skeleton3D) -> int:
	var bone := skeleton.find_bone("mixamorig_Head")
	return bone if bone >= 0 else skeleton.find_bone("mixamorig:Head")


func _restore_head_base() -> void:
	if not _head_gesture.is_empty():
		var skeleton: Skeleton3D = _head_gesture["skeleton"]
		skeleton.set_bone_pose_rotation(_head_gesture["bone"], _head_gesture["base"])


func _advance_head_gesture(delta: float) -> void:
	if _head_gesture.is_empty():
		return
	var skeleton: Skeleton3D = _head_gesture["skeleton"]
	var bone: int = _head_gesture["bone"]
	# Sample the live clip first; never accumulate the previous frame's overlay.
	_head_gesture["base"] = skeleton.get_bone_pose_rotation(bone)
	var elapsed: float = _head_gesture["elapsed"] + delta
	_head_gesture["elapsed"] = elapsed
	var gesture: Dictionary = HEAD_GESTURES[_expression_animation]
	var angles: Array = gesture["angles"]
	if elapsed >= angles.size() * HEAD_KEY_SECONDS:
		cancel_expression()
		play("idle")
		return
	var index := int(elapsed / HEAD_KEY_SECONDS)
	var previous := 0.0 if index == 0 else float(angles[index - 1])
	var angle := lerpf(previous, float(angles[index]), fmod(elapsed, HEAD_KEY_SECONDS) / HEAD_KEY_SECONDS)
	skeleton.set_bone_pose_rotation(bone, (_head_gesture["base"] as Quaternion) * Quaternion(gesture["axis"], angle))


func _apply_bone_blend(targets: Array, weight: float) -> void:
	for index in range(targets.size()):
		var target: Dictionary = targets[index]
		var skeleton := target["skeleton"] as Skeleton3D
		var bone := int(target["bone"])
		var rotation: Quaternion = target["rotation"]
		var position: Vector3 = target["position"]
		if index < _transition_source.size():
			var source := _transition_source[index]
			rotation = (source["rotation"] as Quaternion).slerp(rotation, weight)
			position = (source["position"] as Vector3).lerp(position, weight)
		skeleton.set_bone_pose_rotation(bone, rotation)
		skeleton.set_bone_pose_position(bone, position)


func _apply_breathing(weight: float) -> void:
	if _posture != "sleeping":
		return
	for pose: Dictionary in _posture_target:
		var skeleton := pose["skeleton"] as Skeleton3D
		var bone := int(pose["bone"])
		var bone_name := skeleton.get_bone_name(bone)
		if bone_name not in ["mixamorig:Spine2", "mixamorig_Spine2"]:
			continue
		var rotation := skeleton.get_bone_pose_rotation(bone)
		skeleton.set_bone_pose_rotation(
			bone, rotation * Quaternion(Vector3.RIGHT, sin(_breath_phase) * 0.012 * weight),
		)


func play_expression(expression: String) -> bool:
	if HEAD_GESTURES.has(expression):
		if not supports_head_gestures():
			return false
		cancel_expression()
		play("idle")
		var skeleton := _find_preview_skeleton()
		var bone := _head_bone(skeleton)
		_head_gesture = {"skeleton": skeleton, "bone": bone, "base": skeleton.get_bone_pose_rotation(bone), "elapsed": 0.0}
		_expression_animation = expression
		_actor.set_meta("runtime_expression", expression)
		return true
	var animation_name := expression
	if expression == "happy":
		animation_name = "twist_dance"
	elif expression == "excited":
		animation_name = "jump"
	elif expression == "wave":
		animation_name = "pose_waving"
	if not SHARED_ANIMATIONS.has(animation_name) or not _animation_player.has_animation(animation_name):
		return false
	cancel_expression()
	if animation_name == "idle":
		_animation_player.playback_active = true
		play("idle")
		return true
	_actor.set_meta("runtime_expression", expression)
	_expression_animation = animation_name
	if PREVIEW_POSE_FRAME_RATIOS.has(animation_name) and animation_name != "pose_waving":
		var played := _play_frozen_pose(animation_name)
		if played and _posture.is_empty() and _transition_elapsed < POSTURE_BLEND_SECONDS:
			# An exit blend must converge to this new held pose, not its old idle.
			_posture_target.assign(capture_visual_pose()["bones"])
		_frozen_floor_active = played and _actor is ElfieActor
		_apply_frozen_floor()
		return played
	play(animation_name)
	return true


func play_speech() -> void:
	_actor.set_meta("speaking", true)
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
	_clear_frozen_floor()
	_eyelids.reset()
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
