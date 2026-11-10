extends RefCounted
## Frozen seated pose only: convex body regions from the visible original skin.
## No guessed radius reduction. Tail is excluded by the approved F01 exception.


static func regions(actor: ElfieActor, include_tail: bool = false) -> Dictionary:
	if include_tail:
		var sampler: RefCounted = actor.get_meta("seated_skin_sampler") if actor.has_meta("seated_skin_sampler") else null
		if sampler == null:
			sampler = preload("res://runtime/actor/seated_skin_sampler.gd").new()
			actor.set_meta("seated_skin_sampler",sampler)
		if not sampler.valid(actor): sampler.build(actor,Callable(load("res://runtime/actor/furniture_seated_collision.gd"),"_region"))
		return sampler.sample(actor)
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
				var is_tail := tail >= 0.5 or "tail" in dominant.to_lower()
				if is_tail and not include_tail: continue
				var region := ("tail/" + dominant) if is_tail else _region(dominant)
				if include_tail and region.ends_with("_lower_leg_foot"):
					# Keep the empty inside of the ankle; a calf+foot hull bridges it.
					region = dominant.trim_suffix("ToeBase").trim_suffix("Foot") + "_foot" if "Foot" in dominant or "Toe" in dominant else dominant
				if not groups.has(region): groups[region] = []
				(groups[region] as Array).append(point)
	return groups


static func shapes(actor: ElfieActor, include_tail: bool = false) -> Array[Shape3D]:
	var groups := regions(actor, include_tail)
	var result: Array[Shape3D] = []
	for key: String in groups:
		var points := PackedVector3Array(groups[key])
		if points.size() < 4: continue
		if include_tail:
			# Direct seating retains every skin vertex. Let the native hull
			# builder do this work instead of 26 GDScript passes over each pose.
			var exact := ConvexPolygonShape3D.new()
			exact.points = points
			exact.set_meta("body_region", key)
			result.append(exact)
			continue
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


static func tail_geometry(actor: ElfieActor) -> Dictionary:
	# Skin both sets in actor coordinates so rotating the chair cannot hide
	# a tail/body overlap. The attachment band is retained for pivot fitting.
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	skeleton.force_update_all_bone_transforms()
	var tails := PackedVector3Array()
	var body := PackedVector3Array()
	var to_actor := actor.global_transform.affine_inverse()
	for instance: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if instance.skin == null or instance.mesh == null: continue
		var skin := instance.skin
		var matrices: Array[Transform3D] = []
		var tail_binds: Array[bool] = []
		var mesh_frame := skeleton.global_transform.affine_inverse() * instance.global_transform
		for bind in range(skin.get_bind_count()):
			var bone := skeleton.find_bone(skin.get_bind_name(bind)) if not skin.get_bind_name(bind).is_empty() else skin.get_bind_bone(bind)
			matrices.append(to_actor * skeleton.global_transform * skeleton.get_bone_global_pose(bone) * skin.get_bind_pose(bind) * mesh_frame)
			tail_binds.append("tail" in String(skeleton.get_bone_name(bone)).to_lower())
		for surface in range(instance.mesh.get_surface_count()):
			var arrays := instance.mesh.surface_get_arrays(surface)
			var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			var bones := arrays[Mesh.ARRAY_BONES] as PackedInt32Array
			var weights := arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array
			var stride := 8 if instance.mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS else 4
			for vertex in range(vertices.size()):
				var point := Vector3.ZERO
				var tail_weight := 0.0
				for influence in range(stride):
					var index := vertex * stride + influence
					var bind := bones[index]
					point += (matrices[bind] * vertices[vertex]) * weights[index]
					if tail_binds[bind]: tail_weight += weights[index]
				if tail_weight > 0.8:
					tails.append(point)
				elif tail_weight < 0.1:
					body.append(point)
	var front := -INF
	for point: Vector3 in tails: front = maxf(front, point.z)
	var root := Vector3.ZERO
	var upper := -INF
	var count := 0
	for point: Vector3 in tails:
		if point.z > front - 0.02:
			root += point
			upper = maxf(upper, point.y)
			count += 1
	root /= maxf(count, 1)
	# Hinge at the measured upper edge of the fur attachment, keeping
	# the lower edge outside the rump as this one-joint tail rises.
	return {"tail": tails, "body": body, "root": root, "hinge": Vector3(root.x, upper, root.z)}


static func tail_clearance(actor: ElfieActor, attachment: Vector3 = Vector3.INF) -> Dictionary:
	var geometry := tail_geometry(actor)
	var root := attachment if attachment.is_finite() else geometry["root"] as Vector3
	if not attachment.is_finite():
		var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
		var tail_root := skeleton.find_bone("Tail_01")
		if tail_root >= 0:
			root = actor.to_local(skeleton.to_global(skeleton.get_bone_global_pose(tail_root).origin))
	var cells := {}
	const CELL := 0.035
	for point: Vector3 in geometry["body"]:
		var key := Vector2i(roundi(point.x / CELL), roundi(point.y / CELL))
		var depth: Vector2 = cells.get(key, Vector2(INF, -INF))
		cells[key] = Vector2(minf(depth.x, point.z), maxf(depth.y, point.z))
	var inside := 0
	var first_overlap := {}
	var overlap_indices: Array[int] = []
	var checked := 0
	for index in range((geometry["tail"] as PackedVector3Array).size()):
		var point: Vector3 = geometry["tail"][index]
		if point.distance_to(root) < 0.10: continue
		var key := Vector2i(roundi(point.x / CELL), roundi(point.y / CELL))
		if not cells.has(key): continue
		var depth: Vector2 = cells[key]
		checked += 1
		if point.z > depth.x + 0.012 and point.z < depth.y - 0.012:
			inside += 1
			overlap_indices.append(index)
			if first_overlap.is_empty(): first_overlap = {"point": point, "root": root, "depth": depth, "distance": point.distance_to(root)}
	return {"distal_intrusions": inside, "checked": checked, "first_overlap": first_overlap, "overlap_indices": overlap_indices}


static func hands_clearance(actor: ElfieActor) -> Dictionary:
	var groups := regions(actor, false)
	var cells := {}
	const CELL := 0.02
	for key: String in groups:
		if key != "torso" and "Hips" not in key and "UpLeg" not in key: continue
		for point: Vector3 in groups[key]:
			var cell := Vector2i(roundi(point.x / CELL), roundi(point.y / CELL))
			var depth: Vector2 = cells.get(cell, Vector2(INF, -INF))
			cells[cell] = Vector2(minf(depth.x, point.z), maxf(depth.y, point.z))
	var result := {}
	for side: String in ["Left", "Right"]:
		var points: Array = groups.get(side + "_hand", [])
		var inside := 0
		var first := {}
		for point: Vector3 in points:
			var cell := Vector2i(roundi(point.x / CELL), roundi(point.y / CELL))
			if not cells.has(cell): continue
			var depth: Vector2 = cells[cell]
			if point.z > depth.x + 0.008 and point.z < depth.y - 0.008:
				inside += 1
				if first.is_empty(): first = {"point": point, "depth": depth}
		result[side] = {"vertices": points.size(), "intrusions": inside, "first": first}
	return result

static func prepare_inputs(actor: ElfieActor) -> bool:
	var sampler: RefCounted = actor.get_meta("seated_skin_sampler") if actor.has_meta("seated_skin_sampler") else null
	if sampler == null:
		sampler = preload("res://runtime/actor/seated_skin_sampler.gd").new()
		actor.set_meta("seated_skin_sampler",sampler)
	if not sampler.valid(actor):
		await sampler.build(actor,Callable(load("res://runtime/actor/furniture_seated_collision.gd"),"_region"),true)
	return is_instance_valid(actor) and actor.cycle_available() and sampler.valid(actor)
