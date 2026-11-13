extends SceneTree
## Manual runtime ticks must preserve a sampled expression until an explicit exit.
const RUNTIME := preload("res://runtime/actor/actor_animation_runtime.gd")
const POSES := ["pose_thinking", "pose_victory", "pose_thumbs_up", "pose_hands_on_hips"]
var _failed := false


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var actor := CharacterBody3D.new()
	root.add_child(actor)
	var visual := Node3D.new()
	visual.name = "VisualRoot"
	actor.add_child(visual)
	var skeleton := Skeleton3D.new()
	skeleton.name = "Skeleton3D"
	visual.add_child(skeleton)
	skeleton.add_bone("mixamorig_Head")
	var player := AnimationPlayer.new()
	actor.add_child(player)
	var library := AnimationLibrary.new()
	for clip: String in ["idle", "walking", "pose_waving"] + POSES:
		var animation := Animation.new()
		animation.length = 1.0
		animation.loop_mode = Animation.LOOP_LINEAR if clip in ["idle", "walking"] else Animation.LOOP_NONE
		var track := animation.add_track(Animation.TYPE_ROTATION_3D)
		animation.track_set_path(track, NodePath("VisualRoot/Skeleton3D:mixamorig_Head"))
		animation.rotation_track_insert_key(track, 0.0, Quaternion.IDENTITY)
		animation.rotation_track_insert_key(track, 1.0, Quaternion(Vector3.RIGHT, 1.0))
		library.add_animation(clip, animation)
	player.add_animation_library("", library)
	var runtime := RUNTIME.new()
	runtime.setup(actor, visual, player, false)
	for pose: String in POSES:
		_check(runtime.play_expression(pose), "Expression rejected: " + pose)
		var sample := player.current_animation_position
		var rotation := skeleton.get_bone_pose_rotation(0)
		_check(is_equal_approx(sample, float(RUNTIME.PREVIEW_POSE_FRAME_RATIOS[pose])), "Wrong pose sample: " + pose)
		# Exceed the full clip several times; idle ticks must not release the hold.
		for tick in range(120):
			runtime.play("idle")
			runtime.advance(1.0 / 30.0)
		_check(player.current_animation == pose, "Frozen expression fell back to idle: " + pose)
		_check(is_equal_approx(player.current_animation_position, sample), "Frozen clock advanced: " + pose)
		_check(skeleton.get_bone_pose_rotation(0).is_equal_approx(rotation), "Frozen bone moved: " + pose)
		_check(not player.playback_active, "Frozen playback resumed: " + pose)
		_check(actor.get_meta("runtime_expression", "") == pose, "Frozen expression lost its metadata: " + pose)
		_check(runtime.play_expression("idle"), "Explicit idle rejected")
		runtime.advance(0.3)
		_check(player.current_animation == "idle" and player.playback_active, "Explicit idle did not release hold")
		_check(player.current_animation_position > 0.0, "Idle clock did not resume")
		_check(not actor.has_meta("runtime_expression"), "Idle left expression metadata")
		_check(runtime.play_expression(pose), "Repeated expression rejected")
		runtime.play("walking")
		runtime.advance(0.3)
		_check(player.current_animation == "walking" and player.current_animation_position > 0.0, "Walking did not release hold")
	# Timed expressions and procedural head gestures must still finish normally.
	_check(runtime.play_expression("pose_thinking"), "Replacement setup failed")
	_check(runtime.play_expression("wave"), "Wave replacement rejected")
	runtime.advance(1.1)
	_check(player.current_animation == "idle" and player.playback_active, "Wave did not finish after a frozen pose")
	_check(runtime.play_expression("pose_victory"), "Gesture setup failed")
	_check(runtime.play_expression("nod_head"), "Head gesture replacement rejected")
	runtime.advance(0.4)
	_check(player.current_animation == "idle" and not actor.has_meta("runtime_expression"), "Head gesture did not finish after a frozen pose")
	actor.free()
	if not _failed:
		print("PASS frozen expressions retain sample and bones; idle, walking, wave and nod recover")
	quit(1 if _failed else 0)


func _check(ok: bool, message: String) -> void:
	if not ok:
		_failed = true
		push_error(message)
