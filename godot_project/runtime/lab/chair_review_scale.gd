extends RefCounted
## Diagnostic world-space skin bounds. Never resizes an actor or furniture.


static func measure(actor: ElfieActor) -> Dictionary:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	skeleton.force_update_all_bone_transforms()
	var body := AABB()
	var tail := AABB()
	var has_body := false
	var has_tail := false
	var tail_bones := 0
	for bone in range(skeleton.get_bone_count()):
		if "tail" in String(skeleton.get_bone_name(bone)).to_lower(): tail_bones += 1
	for instance: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if instance.skin == null or instance.mesh == null: continue
		var skin := instance.skin
		var matrices: Array[Transform3D] = []
		var tails: Array[bool] = []
		var mesh_to_skeleton := skeleton.global_transform.affine_inverse() * instance.global_transform
		for bind in range(skin.get_bind_count()):
			var bone := skeleton.find_bone(skin.get_bind_name(bind)) if not skin.get_bind_name(bind).is_empty() else skin.get_bind_bone(bind)
			if bone < 0: return {}
			matrices.append(skeleton.global_transform * skeleton.get_bone_global_pose(bone) * skin.get_bind_pose(bind) * mesh_to_skeleton)
			tails.append("tail" in String(skeleton.get_bone_name(bone)).to_lower())
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
					if tails[bind]: tail_weight += weights[index]
				if tail_weight >= 0.5:
					tail = tail.expand(point) if has_tail else AABB(point, Vector3.ZERO)
					has_tail = true
				else:
					body = body.expand(point) if has_body else AABB(point, Vector3.ZERO)
					has_body = true
	return {"body": body, "tail": tail, "tail_bones": tail_bones, "valid": has_body}


static func seat_size(geometry: Node3D, contact: Transform3D) -> Vector3:
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if extras.get("resident") == "A" and extras.get("piece") == "chair_cushion":
			return (contact.affine_inverse() * mesh.global_transform * mesh.get_aabb()).size
	return Vector3.ZERO


static func seat_height(geometry: Node3D, floor_mesh: MeshInstance3D) -> float:
	var floor_y := (floor_mesh.global_transform * floor_mesh.get_aabb()).end.y
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if extras.get("resident") == "A" and extras.get("piece") == "chair_cushion":
			return (mesh.global_transform * mesh.get_aabb()).end.y - floor_y
	return NAN
