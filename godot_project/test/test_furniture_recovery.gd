extends SceneTree

func _initialize() -> void: call_deferred("run")

func run() -> void:
	create_timer(40.0).timeout.connect(func() -> void: push_error("Furniture recovery check timed out"); quit(1))
	for path: String in ["furniture_motion_runtime", "furniture_cycle", "furniture_contact", "direct_seat_motion", "direct_seat_cycle", "furniture_seated_collision", "chair_swivel", "sleep_cycle", "sleep_arm_pose", "authored_duvet"]:
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
		var clips := preload("res://runtime/actor/chair_clip_sequence.gd").library_for(actor)
		assert(clips != null, "Furniture library failed to retarget for " + species)
		assert(clips.get_animation_list().size() == 1 and clips.has_animation("seated_idle"), "Old mount/stand chain is still reachable")
		var player := actor.get_node("AnimationPlayer") as AnimationPlayer
		player.add_animation_library("chair", clips)
		player.play("chair/seated_idle")
		player.advance(0.0)
		var contact := preload("res://runtime/actor/furniture_contact.gd").butt_point(actor)
		assert(contact.is_finite(), "Direct seating needs real skin contact")
		var hips := actor._furniture_hips()
		var skeleton := hips.skeleton as Skeleton3D
		var pelvis := skeleton.to_global(skeleton.get_bone_global_pose(int(hips.bone)).origin)
		assert(absf((contact-pelvis).dot(actor.global_basis.x.normalized())) < 0.001,"Low skin band shifted the seat sideways")
		for pose: String in ["pose_thinking", "pose_victory", "pose_thumbs_up", "pose_hands_on_hips"]:
			assert(actor.play_runtime_expression(pose), "Lost expression " + pose)
			var sample := player.current_animation_position
			var rotations: Array[Quaternion] = []
			for bone in range(skeleton.get_bone_count()):
				rotations.append(skeleton.get_bone_pose_rotation(bone))
			for tick in range(120):
				actor._process(player.get_animation(pose).length / 60.0)
			assert(player.current_animation == pose and not player.playback_active, "Frozen expression expired: " + species + " " + pose)
			assert(is_equal_approx(player.current_animation_position, sample), "Frozen sample drifted: " + pose)
			for bone in range(skeleton.get_bone_count()):
				assert(skeleton.get_bone_pose_rotation(bone).is_equal_approx(rotations[bone]), "Frozen bone drifted: " + pose)
		assert(actor.play_runtime_expression("idle"))
		assert(player.current_animation == "idle" and player.playback_active, "Stop must leave a frozen expression")
		actor.free()
	print("PASS furniture recovery: both species, direct seated pose only, skin contact and expressions")
	quit(0)
