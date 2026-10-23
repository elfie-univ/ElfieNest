extends SceneTree

const RUNTIME := preload("res://runtime/actor/actor_animation_runtime.gd")
const ACTOR := preload("res://characters/shared/elfie_actor.gd")
var _failed := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	# Synthetic bones keep this regression independent of rooms and imported assets.
	var actor := CharacterBody3D.new()
	root.add_child(actor)
	var visual := Node3D.new()
	actor.add_child(visual)
	visual.scale = Vector3.ONE * 0.7
	var skeleton := Skeleton3D.new()
	visual.add_child(skeleton)
	for part: String in ["Hips", "Spine2", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"]:
		skeleton.add_bone("mixamorig_" + part)
		skeleton.set_bone_pose_scale(skeleton.get_bone_count() - 1, Vector3(1.0, 1.1, 1.0))
	var player := AnimationPlayer.new()
	actor.add_child(player)
	var library := AnimationLibrary.new()
	for clip: String in ["idle", "walking", "pose_waving"]:
		var animation := Animation.new()
		animation.length = 0.5
		animation.loop_mode = Animation.LOOP_NONE if clip == "pose_waving" else Animation.LOOP_LINEAR
		library.add_animation(clip, animation)
	player.add_animation_library("", library)
	var runtime := RUNTIME.new()
	runtime.setup(actor, visual, player, false)
	runtime.play("idle")
	runtime.advance(0.05)
	_require(runtime.play_expression("wave"), "Wave must be supported")
	runtime.play("idle")
	_require(player.current_animation == "pose_waving", "Idle tick interrupted expression")
	runtime.advance(0.6)
	_require(player.current_animation == "idle", "Expression did not recover to idle")
	runtime.play_expression("wave")
	runtime.play("walking")
	_require(player.current_animation == "walking", "Walking must interrupt expression")

	var body_before := actor.transform
	var old_heading := visual.global_basis
	actor.rotation.y = PI / 2.0
	runtime.smooth_heading(old_heading)
	_require(visual.global_basis.is_equal_approx(old_heading), "Visual heading snapped")
	runtime.advance(0.05)
	_require(absf(visual.rotation.y) > 0.01, "Visual turn finished in one frame")
	runtime.advance(2.0)
	_require(absf(visual.rotation.y) < 0.001, "Visual turn failed to settle")
	actor.transform = body_before

	var before := runtime.capture_visual_pose()
	var thigh := skeleton.find_bone("mixamorig_LeftUpLeg")
	skeleton.set_bone_pose_rotation(thigh, Quaternion(Vector3.RIGHT, -PI / 2.0))
	runtime.transition_from(before, "sitting")
	_require(skeleton.get_bone_pose_rotation(thigh).is_equal_approx(Quaternion.IDENTITY), "Sit entry snapped")
	runtime.advance(0.15)
	var angle := skeleton.get_bone_pose_rotation(thigh).get_angle()
	_require(angle > 0.01 and angle < PI / 2.0, "Sit entry did not interpolate")
	var interrupted := runtime.capture_visual_pose()
	skeleton.set_bone_pose_rotation(thigh, Quaternion.IDENTITY)
	runtime.transition_from(interrupted)
	runtime.advance(1.0)
	_require(skeleton.get_bone_pose_rotation(thigh).is_equal_approx(Quaternion.IDENTITY), "Interrupted sit did not recover")

	before = runtime.capture_visual_pose()
	visual.rotation.x = -PI / 2.0
	runtime.transition_from(before, "sleeping")
	runtime.advance(1.0)
	var chest := skeleton.find_bone("mixamorig_Spine2")
	var breath_a := skeleton.get_bone_pose_rotation(chest)
	runtime.advance(1.0)
	_require(not skeleton.get_bone_pose_rotation(chest).is_equal_approx(breath_a), "Sleeping chest did not breathe")
	_require(actor.transform.is_equal_approx(body_before), "Animation moved physical actor")
	_require(visual.scale.is_equal_approx(Vector3.ONE * 0.7), "Animation changed visual size")
	for bone in range(skeleton.get_bone_count()):
		_require(skeleton.get_bone_pose_scale(bone).is_equal_approx(Vector3(1.0, 1.1, 1.0)), "Animation changed body proportions")
	before = runtime.capture_visual_pose()
	visual.rotation = Vector3.ZERO
	skeleton.set_bone_pose_rotation(chest, Quaternion.IDENTITY)
	runtime.transition_from(before)
	runtime.advance(2.0)
	_require(visual.rotation.is_zero_approx(), "Sleep exit did not return upright")
	_require(skeleton.get_bone_pose_rotation(chest).is_equal_approx(Quaternion.IDENTITY), "Breathing survived sleep exit")
	actor.free()
	_test_actor_wiring()
	quit(1 if _failed else 0)


func _test_actor_wiring() -> void:
	# Exercise the actual actor posture helpers without physics, rooms or GLB imports.
	var actor := ACTOR.new()
	actor.install_shared_animations = false
	var visual := Node3D.new()
	visual.name = "VisualRoot"
	actor.add_child(visual)
	var skeleton := Skeleton3D.new()
	visual.add_child(skeleton)
	for part: String in ["Hips", "Spine2", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"]:
		skeleton.add_bone("mixamorig_" + part)
	var collision := CollisionShape3D.new()
	collision.name = "CollisionShape3D"
	collision.shape = CapsuleShape3D.new()
	actor.add_child(collision)
	var player := AnimationPlayer.new()
	player.name = "AnimationPlayer"
	actor.add_child(player)
	root.add_child(actor)
	actor.set_physics_process(false)
	var marker := Marker3D.new()
	root.add_child(marker)
	marker.set_meta("kind", "chair")
	marker.set_meta("zone_id", "test")
	marker.set_meta("interaction_posture", "sitting")
	marker.set_meta("interaction_transform", Transform3D.IDENTITY)
	_require(actor.enter_furniture(marker, "chair") == "", "Existing sit command failed")
	_require(actor.runtime_posture() == "sitting", "Visual transition changed semantic posture")
	var thigh := skeleton.find_bone("mixamorig_LeftUpLeg")
	_require(skeleton.get_bone_pose_rotation(thigh).is_equal_approx(Quaternion.IDENTITY), "Actor did not wire sit transition")
	actor._process(1.0)
	_require(skeleton.get_bone_pose_rotation(thigh).get_angle() > 1.0, "Actor process did not advance sit")
	var contact := actor.global_transform
	actor.play_runtime_speech()
	actor._process(0.1)
	_require(actor.global_transform.is_equal_approx(contact), "Speech moved seated contact")
	marker.free()
	actor.free()


func _require(condition: bool, message: String) -> void:
	if not condition:
		_failed = true
		push_error(message)
