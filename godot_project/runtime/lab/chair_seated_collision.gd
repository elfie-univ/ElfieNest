extends RefCounted
## Frozen seated pose only: convex body regions from the visible original skin.
## No guessed radius reduction. Tail is excluded by the approved F01 exception.


static func shapes(actor: ElfieActor) -> Array[Shape3D]:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	skeleton.force_update_all_bone_transforms()
	var groups: Dictionary = {}
	var to_actor := actor.global_transform.affine_inverse()
	for instance: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if instance.skin == null or instance.mesh == null: continue
		var skin := instance.skin
		var matrices: Array[Transform3D] = []
		var names: Array[String] = []
		var mesh_frame := skeleton.global_transform.affine_inverse() * instance.global_transform
		for bind in range(skin.get_bind_count()):
			var bone := skeleton.find_bone(skin.get_bind_name(bind)) if not skin.get_bind_name(bind).is_empty() else skin.get_bind_bone(bind)
			matrices.append(to_actor * skeleton.global_transform * skeleton.get_bone_global_pose(bone) * skin.get_bind_pose(bind) * mesh_frame)
			names.append(String(skeleton.get_bone_name(bone)))
		for surface in range(instance.mesh.get_surface_count()):
			var arrays := instance.mesh.surface_get_arrays(surface)
			var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			var bones := arrays[Mesh.ARRAY_BONES] as PackedInt32Array
			var weights := arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array
			var stride := 8 if instance.mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS else 4
			for vertex in range(vertices.size()):
				var point := Vector3.ZERO
				var dominant := ""
				var weight := 0.0
				var tail := 0.0
				for influence in range(stride):
					var index := vertex * stride + influence
					var bind := bones[index]
					point += (matrices[bind] * vertices[vertex]) * weights[index]
					if "tail" in names[bind].to_lower(): tail += weights[index]
					if weights[index] > weight:
						weight = weights[index]
						dominant = names[bind]
				if tail >= 0.5 or "tail" in dominant.to_lower(): continue
				var region := _region(dominant)
				if not groups.has(region): groups[region] = []
				(groups[region] as Array).append(point)
	var result: Array[Shape3D] = []
	for key: String in groups:
		var points := PackedVector3Array(groups[key])
		if points.size() < 4: continue
		# Conservative 26-plane envelope: every original skin point lies inside.
		# Unlike vertex decimation it cannot shrink away a protruding body part.
		# This is a collision proxy only; render meshes remain untouched.
		var planes: Array[Plane] = []
		for x in range(-1, 2):
			for y in range(-1, 2):
				for z in range(-1, 2):
					if x == 0 and y == 0 and z == 0: continue
					var normal := Vector3(x, y, z).normalized()
					var support := -INF
					for point: Vector3 in points: support = maxf(support, normal.dot(point))
					planes.append(Plane(normal, support + 0.00005))
		var hull := ConvexPolygonShape3D.new()
		# The coarse plane envelope loses too much clearance around small
		# fingers near the desktop. Keep all hand vertices for an exact hull.
		hull.points = points if key.ends_with("_hand") else Geometry3D.compute_convex_mesh_points(planes)
		hull.set_meta("body_region", key)
		result.append(hull)
	return result


static func _region(bone: String) -> String:
	if "Head" in bone or "Neck" in bone: return "head_neck"
	if "Spine" in bone or "Shoulder" in bone: return "torso"
	if "Hips" in bone or "UpLeg" in bone: return bone
	for side: String in ["Left", "Right"]:
		if side not in bone: continue
		# Preserve the elbow gap. A single hull across upper arm, bent forearm
		# and hand can hit the desk even when the restored source pose is clear.
		if "ForeArm" in bone: return side + "_forearm"
		if "Arm" in bone: return side + "_upper_arm"
		if "Hand" in bone: return side + "_hand"
		if "Leg" in bone or "Foot" in bone or "Toe" in bone: return side + "_lower_leg_foot"
	return bone
