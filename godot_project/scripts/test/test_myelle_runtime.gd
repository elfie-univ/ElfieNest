extends SceneTree

const CATALOG := preload("res://runtime/species_catalog.gd")
const APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const READINESS := preload("res://scripts/test/project_readiness.gd")


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	if not await READINESS.wait_until_ready(self):
		_fail("Import readiness timed out")
		return
	var catalog := CATALOG.discover_actor_scenes()
	for species_id: String in ["saevi", "tovren", "myelle"]:
		if not catalog.has(species_id):
			_fail("Missing validated species: %s" % species_id)
			return
	var actor := (catalog["myelle"] as PackedScene).instantiate() as CharacterBody3D
	root.add_child(actor)
	actor.set_physics_process(false)
	var visual := actor.get_node("VisualRoot") as Node3D
	var collision := actor.get_node("CollisionShape3D") as CollisionShape3D
	var skeleton := visual.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var animation_root := player.get_node(player.root_node)
	var tail_indices: Array[int] = []
	for index in range(1, 5):
		var bone := skeleton.find_bone("Tail_%02d" % index)
		var parent := skeleton.find_bone("mixamorig_Hips" if index == 1 else "Tail_%02d" % (index - 1))
		if bone < 0 or skeleton.get_bone_parent(bone) != parent:
			_fail("Tail hierarchy is not attached to Hips")
			return
		tail_indices.append(bone)
	for animation_name: String in CATALOG.REQUIRED_ANIMATIONS:
		if not player.has_animation(animation_name):
			_fail("Missing installed animation: %s" % animation_name)
			return
		var animation := player.get_animation(animation_name)
		for track in range(animation.get_track_count()):
			var path := animation.track_get_path(track)
			if animation_root.get_node_or_null(NodePath(path.get_concatenated_names())) == null:
				_fail("Unresolved animation track: %s" % path)
				return
			if String(path).contains("Tail_"):
				_fail("A shared action unexpectedly controls tail bones")
				return
		player.play(animation_name)
		player.seek(0.0, true)
		var starting_pose: Array[Quaternion] = []
		for bone in range(skeleton.get_bone_count()):
			starting_pose.append(skeleton.get_bone_pose_rotation(bone))
		var changed := false
		for ratio: float in [0.0, 0.25, 0.5, 0.75]:
			player.seek(animation.length * ratio, true)
			for bone in range(skeleton.get_bone_count()):
				changed = changed or not skeleton.get_bone_pose_rotation(bone).is_equal_approx(starting_pose[bone])
				if not skeleton.get_bone_global_pose(bone).is_finite():
					_fail("Non-finite animated bone: %s" % animation_name)
					return
		if not changed:
			_fail("Animation did not change a bone pose: %s" % animation_name)
			return
		print("MYELLE_ACTION:%s length=%.3f tracks=%d" % [animation_name, animation.length, animation.get_track_count()])
	player.stop()
	skeleton.reset_bone_poses()
	var hips := skeleton.find_bone("mixamorig_Hips")
	var before: Array[Transform3D] = []
	for bone in tail_indices:
		before.append(skeleton.get_bone_global_pose(hips).affine_inverse() * skeleton.get_bone_global_pose(bone))
	for name: String in ["mixamorig_LeftUpLeg", "mixamorig_RightUpLeg", "mixamorig_LeftLeg", "mixamorig_RightLeg"]:
		var leg := skeleton.find_bone(name)
		skeleton.set_bone_pose_rotation(leg, Quaternion(Vector3.RIGHT, 0.6))
		for index in range(4):
			var relative := skeleton.get_bone_global_pose(hips).affine_inverse() * skeleton.get_bone_global_pose(tail_indices[index])
			if not relative.is_equal_approx(before[index]):
				_fail("Leg rotation changed tail transform")
				return
		skeleton.reset_bone_poses()
	var head := skeleton.find_bone("mixamorig_Head")
	var head_scale := skeleton.get_bone_pose_scale(head)
	APPEARANCE.apply(visual, collision, {
		"height_scale": 1.08, "build_scale": 1.08,
		"bone_scales": {"HeadScale": 1.08},
		"material_parameters": {"palette_id": "gray", "primary_color_id": "gray"},
	}, "myelle")
	if skeleton.get_bone_pose_scale(head) == head_scale or not collision.shape is CapsuleShape3D:
		_fail("Appearance or capsule application failed")
		return
	var material := (visual.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D).get_surface_override_material(0) as ShaderMaterial
	if material == null or material.get_shader_parameter("appearance_region_source_texture") == null:
		_fail("Runtime coat material lost its source texture")
		return
	if material.get_shader_parameter("appearance_species_id") != 2:
		_fail("Myelle used another species' appearance binding")
		return
	var wall := StaticBody3D.new()
	var wall_collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.2, 5.0, 5.0)
	wall_collision.shape = box
	wall.add_child(wall_collision)
	wall.position = Vector3(1.5, 1.0, 0.0)
	root.add_child(wall)
	await physics_frame
	var hit := actor.move_and_collide(Vector3(3.0, 0.0, 0.0))
	if hit == null or actor.position.x >= wall.position.x:
		_fail("Myelle capsule passed through a wall")
		return
	wall.free()
	actor.free()
	print("MYELLE_RUNTIME_PASS: three validated species, 13 actions, independent tail hierarchy, appearance and capsule")
	quit()


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
