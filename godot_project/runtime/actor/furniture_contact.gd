extends RefCounted
## CPU sampling of the actual skinned foot vertices, not a pelvis-height proxy.


static func ground(actor: ElfieActor, floor_y: float) -> float:
	var sole := sole_y(actor)
	if not is_finite(sole): return INF
	var offset := floor_y - sole
	(actor.get_node("VisualRoot") as Node3D).global_position.y += offset
	return offset


static func sole_y(actor: ElfieActor) -> float:
	return float(_sample(actor, false).get("min_y", INF))


static func butt_point(actor: ElfieActor) -> Vector3:
	return _sample(actor, true).get("point", Vector3.INF) as Vector3


static func _sample(actor: ElfieActor, hips: bool) -> Dictionary:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	skeleton.force_update_all_bone_transforms()
	var lowest := INF
	var selected := PackedVector3Array()
	var threshold := 0.6 if hips else 0.8
	for instance: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if instance.skin == null or instance.mesh == null: continue
		var skin := instance.skin
		var matrices: Array[Transform3D] = []
		var feet: Array[bool] = []
		var mesh_to_skeleton := skeleton.global_transform.affine_inverse() * instance.global_transform
		for bind in range(skin.get_bind_count()):
			var bone := skeleton.find_bone(skin.get_bind_name(bind)) if not skin.get_bind_name(bind).is_empty() else skin.get_bind_bone(bind)
			if bone < 0: return {}
			matrices.append(skeleton.global_transform * skeleton.get_bone_global_pose(bone) * skin.get_bind_pose(bind) * mesh_to_skeleton)
			var name := String(skeleton.get_bone_name(bone)).to_lower()
			feet.append(name.ends_with("hips") if hips else ("foot" in name or "toe" in name))
		for surface in range(instance.mesh.get_surface_count()):
			var arrays := instance.mesh.surface_get_arrays(surface)
			var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			var bones := arrays[Mesh.ARRAY_BONES] as PackedInt32Array
			var weights := arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array
			var stride := 8 if instance.mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS else 4
			for vertex in range(vertices.size()):
				var begin := vertex * stride
				var end := mini(begin + stride, weights.size())
				var contact_weight := 0.0
				for index in range(begin, end):
					if feet[bones[index]]: contact_weight += weights[index]
				if contact_weight <= threshold: continue
				var point := Vector3.ZERO
				for index in range(begin, end):
					point += (matrices[bones[index]] * vertices[vertex]) * weights[index]
				lowest = minf(lowest, point.y)
				selected.append(point)
	if not is_finite(lowest): return {}
	var contact := Vector3.ZERO
	var count := 0
	for point: Vector3 in selected:
		if point.y <= lowest + 0.015:
			contact += point
			count += 1
	contact /= maxf(count, 1.0)
	if hips:
		# A tilted pelvis can put only one side in the lowest 15 mm band.
		# That band sets contact height, not a sideways seating offset.
		var bone := int(actor._furniture_hips()["bone"])
		var pelvis := actor.to_local(skeleton.to_global(skeleton.get_bone_global_pose(bone).origin))
		var local := actor.to_local(contact)
		local.x = pelvis.x
		contact = actor.to_global(local)
	return {"min_y": lowest, "point": contact}
