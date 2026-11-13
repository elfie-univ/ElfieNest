extends RefCounted
## Retarget the resting seated pose; travel and exit use the authored direct curves.

static func library_for(actor: ElfieActor) -> AnimationLibrary:
	var result := AnimationLibrary.new()
	var clip := _retarget(load("res://characters/animation/candidates/Sitting Idle.fbx") as AnimationLibrary,actor,false)
	if clip == null: return null
	clip.loop_mode = Animation.LOOP_LINEAR
	var idle := locomotion_for(actor).get_animation("idle")
	preload("res://runtime/actor/chair_dog_leg_keys.gd").bake(clip,"seated_idle",actor,idle)
	result.add_animation("seated_idle",clip)
	return result

static func locomotion_for(actor: ElfieActor) -> AnimationLibrary:
	var result := AnimationLibrary.new()
	for key: String in ["idle", "walking"]:
		var source := load("res://characters/animation/%s.fbx" % key) as AnimationLibrary
		var clip := _retarget(source, actor, true)
		if clip == null: return null
		clip.loop_mode = Animation.LOOP_LINEAR
		result.add_animation(key, clip)
	return result


static func _retarget(source: AnimationLibrary, actor: ElfieActor, in_place: bool) -> Animation:
	if source == null or not source.has_meta("mixamo_source_rest"):
		push_error("Missing imported source rest; cannot safely retarget Mixamo clip")
		return null
	var original := source.get_animation(source.get_animation_list()[0])
	var clip := original.duplicate(true) as Animation
	var metadata: Dictionary = source.get_meta("mixamo_source_rest")
	var source_bones: Dictionary = metadata["bones"]
	var source_frame: Transform3D = metadata["frame"]
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var animation_root := player.get_node(player.root_node)
	var visual := actor.get_node("VisualRoot") as Node3D
	var target := actor._furniture_hips()["skeleton"] as Skeleton3D
	var target_frame := visual.global_transform.affine_inverse() * target.global_transform
	var units := source_frame.basis.get_scale() / target_frame.basis.get_scale()
	for track in range(clip.get_track_count() - 1, -1, -1):
		var path := clip.track_get_path(track)
		if animation_root.get_node_or_null(NodePath(path.get_concatenated_names())) != target or path.get_subname_count() != 1:
			push_error("Retarget track has no target skeleton: %s (%s)" % [path, source.resource_path])
			return null
		var name := String(path.get_subname(0))
		var bone := target.find_bone(name)
		if bone < 0 and "Hand" in name:
			# The target species has fewer finger joints. Keep all body tracks;
			# omit only unsupported finger articulation, as in the raw viewer.
			clip.remove_track(track)
			continue
		if bone < 0 or not source_bones.has(name):
			push_error("Retarget rest missing for %s (%s); source bones %s" % [name, source.resource_path, source_bones.keys()])
			return null
		var source_rest: Transform3D = source_bones[name]["rest"]
		var source_parent: Transform3D = source_bones[name]["parent_rest"]
		var target_rest := target.get_bone_rest(bone)
		var parent := target.get_bone_parent(bone)
		var target_parent := target.get_bone_global_rest(parent) if parent >= 0 else Transform3D.IDENTITY
		var source_parent_basis := (source_frame.basis * source_parent.basis).orthonormalized()
		var target_parent_basis := (target_frame.basis * target_parent.basis).orthonormalized()
		var pre := target_parent_basis.inverse() * source_parent_basis
		var post := source_rest.basis.orthonormalized().inverse() * pre.inverse() * target_rest.basis.orthonormalized()
		var first := Vector3.ZERO
		for key in range(clip.track_get_key_count(track)):
			if clip.track_get_type(track) == Animation.TYPE_POSITION_3D:
				var value: Vector3 = pre * ((original.track_get_key_value(track, key) as Vector3) - source_rest.origin) * units + target_rest.origin
				if key == 0: first = value
				# Physical navigation owns horizontal travel for locomotion only.
				if in_place:
					value.x = first.x
					value.z = first.z
				clip.track_set_key_value(track, key, value)
			elif clip.track_get_type(track) == Animation.TYPE_ROTATION_3D:
				var source_rotation := original.track_get_key_value(track, key) as Quaternion
				var rotation := (pre * Basis(source_rotation) * post).get_rotation_quaternion()
				# These rigs retain canonical Mixamo upper-limb axes, but their
				# authored arm rest is already lowered/bent. Applying the source
				# T-pose delta to that silhouette lowers the arms a second time.
				# Godot 4 clips store absolute local bone poses, not rest deltas.
				if _is_upper_limb(name): rotation = source_rotation
				clip.track_set_key_value(track, key, rotation)
	return clip


static func _is_upper_limb(bone: String) -> bool:
	for side: String in ["Left", "Right"]:
		var prefix := "mixamorig_" + side
		# Finger joints retain their species-specific rest correction. The
		# shared canonical axes above concern the shoulder, elbow and wrist.
		if bone in [prefix + "Shoulder", prefix + "Arm", prefix + "ForeArm", prefix + "Hand"]: return true
	return false
