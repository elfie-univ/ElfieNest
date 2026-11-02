extends RefCounted
## Bake a dog-sized two-bone leg retarget into clip copies, not per-frame IK.
## Source body motion/timing and bone lengths stay intact; target poses are authored.

const EDITS := preload("res://characters/animation/candidates/dog_chair_contact_edits.tres")


static func bake(clip: Animation, key: String, actor: ElfieActor, idle: Animation, standing_lift: Vector2 = Vector2.ZERO) -> void:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var saved: Array[Transform3D] = []
	for bone in range(skeleton.get_bone_count()): saved.append(skeleton.get_bone_pose(bone))
	_apply(skeleton, idle, 0.0)
	var hips := skeleton.find_bone("mixamorig_Hips")
	var idle_frame := _heading(skeleton, hips)
	var foot_frames: Dictionary = {}
	var tracks: Dictionary = {}
	var source := clip.duplicate(true) as Animation
	for side: String in ["Left", "Right"]:
		var foot := skeleton.find_bone("mixamorig_" + side + "Foot")
		var toe := skeleton.find_bone("mixamorig_" + side + "ToeBase")
		var toe_direction := idle_frame.inverse() * (_world(skeleton, toe).origin - _world(skeleton, foot).origin)
		var straighten := Basis(Vector3.UP, -atan2(toe_direction.x, toe_direction.z))
		foot_frames[side] = straighten * idle_frame.inverse() * _world(skeleton, foot).basis
		for suffix: String in ["UpLeg", "Leg", "Foot", "ToeBase"]:
			var bone_name := "mixamorig_" + side + suffix
			var path := NodePath("Skeleton3D:" + bone_name)
			var old := clip.find_track(path, Animation.TYPE_ROTATION_3D)
			if old >= 0: clip.remove_track(old)
	# Resolve indices only after removal, since removing a track shifts later ones.
	for side: String in ["Left", "Right"]:
		for suffix: String in ["UpLeg", "Leg", "Foot", "ToeBase"]:
			var bone_name := "mixamorig_" + side + suffix
			var track := clip.add_track(Animation.TYPE_ROTATION_3D)
			clip.track_set_path(track, NodePath("Skeleton3D:" + bone_name))
			tracks[bone_name] = track
	for frame in range(int(ceil(clip.length * 30.0)) + 1):
		var time := minf(float(frame) / 30.0, clip.length)
		_apply(skeleton, source, time)
		var seated := 1.0 if key == "seated_idle" else 0.0
		if key in ["sit_down", "stand_up"]:
			var edit := EDITS.get_animation(key)
			seated = absf(edit.position_track_interpolate(0, time).y / edit.position_track_interpolate(0, edit.length).y)
			if key == "stand_up": seated = 1.0 - seated
		var heading := _heading(skeleton, hips)
		for side: String in ["Left", "Right"]:
			var upper := skeleton.find_bone("mixamorig_" + side + "UpLeg")
			var lower := skeleton.find_bone("mixamorig_" + side + "Leg")
			var foot := skeleton.find_bone("mixamorig_" + side + "Foot")
			var a := _world(skeleton, upper).origin
			var b := _world(skeleton, lower).origin
			var c := _world(skeleton, foot).origin
			var upper_length := a.distance_to(b)
			var lower_length := b.distance_to(c)
			# Retain the downloaded turn/rise foot lift and forward travel. Only
			# reduce lateral splay; blend into the authored dangling seated feet.
			var ankle := heading.inverse() * (c - a)
			ankle.y += standing_lift.x if side == "Left" else standing_lift.y
			var lateral := (heading.inverse() * (a - _world(skeleton, hips).origin)).x
			ankle.x = -signf(lateral) * float(EDITS.get_meta("standing_ankle_inset"))
			if key == "stand_up": ankle.y += float(EDITS.get_meta("standing_sole_lift")) * (1.0 - seated)
			ankle = ankle.lerp(EDITS.get_meta("seated_ankle") as Vector3, seated)
			var source_foot := _world(skeleton, foot).basis.orthonormalized()
			var target := a + heading * ankle
			var direction := (target - a).normalized()
			var distance := clampf(a.distance_to(target), absf(upper_length - lower_length) + 0.001, upper_length + lower_length - 0.001)
			target = a + direction * distance
			var along := (upper_length * upper_length + distance * distance - lower_length * lower_length) / (2.0 * distance)
			var pole := (heading.z - direction * heading.z.dot(direction)).normalized()
			var knee := a + direction * along + pole * sqrt(maxf(0.0, upper_length * upper_length - along * along))
			_rotate_toward(skeleton, upper, b - a, knee - a)
			b = _world(skeleton, lower).origin
			c = _world(skeleton, foot).origin
			_rotate_toward(skeleton, lower, c - b, target - b)
			var foot_blend := 0.65 if key == "turn_left_90" else 1.0
			_set_world_basis(skeleton, foot, source_foot.slerp((heading * (foot_frames[side] as Basis)).orthonormalized(), foot_blend))
			# Keep the downloaded idle toe orientation, not the sitting toe curl.
			var toe := skeleton.find_bone("mixamorig_" + side + "ToeBase")
			var toe_track := idle.find_track(NodePath("Skeleton3D:" + String(skeleton.get_bone_name(toe))), Animation.TYPE_ROTATION_3D)
			if toe_track >= 0: skeleton.set_bone_pose_rotation(toe, idle.rotation_track_interpolate(toe_track, 0.0))
		for bone_name: String in tracks:
			clip.rotation_track_insert_key(int(tracks[bone_name]), time, skeleton.get_bone_pose_rotation(skeleton.find_bone(bone_name)))
	for bone in range(saved.size()):
		skeleton.set_bone_pose_position(bone, saved[bone].origin)
		skeleton.set_bone_pose_rotation(bone, saved[bone].basis.get_rotation_quaternion())


static func _apply(skeleton: Skeleton3D, clip: Animation, time: float) -> void:
	for track in range(clip.get_track_count()):
		var path := clip.track_get_path(track)
		if path.get_subname_count() != 1: continue
		var bone := skeleton.find_bone(path.get_subname(0))
		if bone < 0: continue
		if clip.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			skeleton.set_bone_pose_rotation(bone, clip.rotation_track_interpolate(track, time))
		elif clip.track_get_type(track) == Animation.TYPE_POSITION_3D:
			skeleton.set_bone_pose_position(bone, clip.position_track_interpolate(track, time))


static func _world(skeleton: Skeleton3D, bone: int) -> Transform3D:
	return skeleton.global_transform * skeleton.get_bone_global_pose(bone)


static func _heading(skeleton: Skeleton3D, hips: int) -> Basis:
	return Basis(Vector3.UP, _world(skeleton, hips).basis.orthonormalized().get_euler().y)


static func _rotate_toward(skeleton: Skeleton3D, bone: int, from: Vector3, to: Vector3) -> void:
	_set_world_basis(skeleton, bone, Basis(Quaternion(from.normalized(), to.normalized())) * _world(skeleton, bone).basis)


static func _set_world_basis(skeleton: Skeleton3D, bone: int, basis: Basis) -> void:
	var parent := skeleton.get_bone_parent(bone)
	var frame := _world(skeleton, parent).basis if parent >= 0 else skeleton.global_basis
	skeleton.set_bone_pose_rotation(bone, (frame.inverse() * basis).orthonormalized().get_rotation_quaternion())
