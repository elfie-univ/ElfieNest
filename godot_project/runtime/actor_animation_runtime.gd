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
) -> void:
	_actor = actor
	_visual_root = visual_root
	_animation_player = animation_player
	if install_shared:
		_install_shared_animations()


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
