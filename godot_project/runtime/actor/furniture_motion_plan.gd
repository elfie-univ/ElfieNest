extends RefCounted
## Measure downloaded motion on a hidden, nonphysical probe. Never warp a visible actor.

const CONTACT := preload("res://runtime/actor/furniture_contact.gd")


static func measure(probe: ElfieActor) -> Dictionary:
	probe.visible = false
	probe.set_physics_process(false)
	probe.set_process(false)
	probe.collision_layer = 0
	probe.collision_mask = 0
	CONTACT.ground(probe, 0.0)
	var skeleton := probe._furniture_hips()["skeleton"] as Skeleton3D
	var bone := int(probe._furniture_hips()["bone"])
	var initial := skeleton.get_bone_pose_rotation(bone)
	probe.call("begin_sequence", CONTACT.butt_point(probe).y)
	var player := probe.get_node("AnimationPlayer") as AnimationPlayer
	for key: String in ["step_up", "turn_left_90", "turn_left_90", "sit_down", "seated_idle"]:
		if not bool(probe.call("start_clip", key)): return {}
		for frame in range(int(ceil(player.current_animation_length * 60.0)) + 1):
			probe.call("_physics_process", 1.0 / 60.0)
	var rotation := skeleton.get_bone_pose_rotation(bone) * initial.inverse()
	var frame := skeleton.global_basis.orthonormalized()
	var yaw := (frame * Basis(rotation) * frame.inverse()).get_euler().y
	# Build the frozen seated body during fixture loading, not mid-animation.
	var seated_shapes := preload("res://runtime/actor/furniture_seated_collision.gd").shapes(probe)
	return {"contact_offset": CONTACT.butt_point(probe), "yaw": yaw, "seated_shapes": seated_shapes}


static func approach(contact: Transform3D, measured: Dictionary) -> Transform3D:
	var heading := contact.basis * Basis(Vector3.UP, -float(measured["yaw"]))
	var offset := heading * (measured["contact_offset"] as Vector3)
	return Transform3D(heading, contact.origin - offset)


static func fit_sofa_mount(library: AnimationLibrary, actor: ElfieActor, height_delta: float) -> void:
	# Adapt the approved mount/dismount edit to the measured skin and seat.
	# Preserve its timing/easing and keep real root-motion collisions active.
	var edits := preload("res://characters/animation/candidates/dog_sofa_contact_edits.tres")
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var path := NodePath("Skeleton3D:" + str(skeleton.get_bone_name(int(actor._furniture_hips()["bone"]))))
	var local_delta := skeleton.global_basis.inverse() * Vector3.UP * height_delta
	for key: String in ["step_up", "jump_down"]:
		var clip := library.get_animation(key)
		var curve := edits.get_animation(key)
		var track := clip.find_track(path, Animation.TYPE_POSITION_3D)
		var end := curve.position_track_interpolate(0, curve.length).y
		for index in range(clip.track_get_key_count(track)):
			var time := clip.track_get_key_time(track, index)
			var weight := curve.position_track_interpolate(0, time).y / end
			var direction := 1.0 if key == "step_up" else -1.0
			clip.track_set_key_value(track, index, (clip.track_get_key_value(track, index) as Vector3) + local_delta * weight * direction)
