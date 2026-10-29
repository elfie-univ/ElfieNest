extends RefCounted
## Measure downloaded motion on a hidden, nonphysical probe. Never warp a visible actor.

const CONTACT := preload("res://runtime/lab/chair_review_contact.gd")


static func seating_contact(geometry: Node3D, original: Transform3D) -> Dictionary:
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if extras.get("resident") == "A" and extras.get("source_name") == "Chair | central tall back petal":
			# Mesh +Z is an export axis, not the chair's usable forward direction.
			var back := (mesh.global_transform * mesh.get_aabb()).get_center()
			var forward := original.origin - back
			forward.y = 0.0
			if forward.length() < 0.01: return {}
			return {"transform": Transform3D(Basis(Vector3.UP, atan2(forward.x, forward.z)), original.origin)}
	return {}


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
	var seated_shapes := preload("res://runtime/lab/chair_seated_collision.gd").shapes(probe)
	return {"contact_offset": CONTACT.butt_point(probe), "yaw": yaw, "seated_shapes": seated_shapes}


static func approach(contact: Transform3D, measured: Dictionary) -> Transform3D:
	var heading := contact.basis * Basis(Vector3.UP, -float(measured["yaw"]))
	var offset := heading * (measured["contact_offset"] as Vector3)
	return Transform3D(heading, contact.origin - offset)
