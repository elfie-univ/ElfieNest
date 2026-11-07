extends SceneTree

func _initialize() -> void: call_deferred("run")

func run() -> void:
	create_timer(40.0).timeout.connect(func() -> void: push_error("Furniture recovery check timed out"); quit(1))
	for path: String in ["furniture_motion_runtime", "furniture_cycle", "furniture_contact", "furniture_motion_plan", "furniture_seated_collision", "chair_swivel", "sleep_cycle", "sleep_arm_pose", "authored_duvet"]:
		var resource := load("res://runtime/actor/" + path + ".gd") as GDScript
		if resource == null or not resource.can_instantiate():
			push_error("Recovered runtime does not compile: " + path)
			quit(1)
			return
	for species: String in ["tovren", "saevi"]:
		var actor := (load("res://characters/" + species + "/" + species + ".tscn") as PackedScene).instantiate() as ElfieActor
		root.add_child(actor)
		actor.configure("restored-" + species, Vector3.ZERO)
		actor.set_physics_process(false)
		actor.set_process(false)
		assert(actor.has_method("play_furniture_cycle"))
		var clips := preload("res://runtime/actor/chair_clip_sequence.gd").library_for(actor, true)
		assert(clips != null, "Furniture library failed to retarget for " + species)
		for clip: String in ["step_up", "turn_left_90", "sit_down", "seated_idle", "stand_up", "jump_down"]:
			assert(clips.has_animation(clip), "Missing restored furniture stage " + clip)
		var player := actor.get_node("AnimationPlayer") as AnimationPlayer
		player.add_animation_library("chair", clips)
		var measured := preload("res://runtime/actor/furniture_motion_plan.gd").measure(actor)
		assert(not measured.is_empty(), "Cannot measure restored root motion")
		assert((measured.contact_offset as Vector3).is_finite())
		actor.call("end_sequence")
		for pose: String in ["pose_thinking", "pose_victory", "pose_thumbs_up", "pose_hands_on_hips"]:
			assert(actor.play_runtime_expression(pose), "Lost expression " + pose)
		assert(actor.play_runtime_expression("idle"))
		assert(player.current_animation == "idle" and player.playback_active, "Stop must leave a frozen expression")
		actor.free()
	print("PASS furniture recovery: both species, complete retargeted clip chains, root motion, skin contact and expressions")
	quit(0)
