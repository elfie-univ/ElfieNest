extends RefCounted
## Diagnostic actual skinned vertices, with only the explicitly allowed tail omitted.


static func sample(actor: ElfieActor, _chair: Node3D, frame_delta: Transform3D = Transform3D.IDENTITY, carrier: Array[RID] = []) -> Dictionary:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	skeleton.force_update_all_bone_transforms()
	var result := {}
	var query := PhysicsPointQueryParameters3D.new()
	var omitted := carrier.duplicate()
	omitted.append(actor.get_rid())
	query.exclude = omitted
	var space := actor.get_world_3d().direct_space_state
	for instance: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if instance.skin == null or instance.mesh == null: continue
		var skin := instance.skin
		var matrices: Array[Transform3D] = []
		var names: Array[String] = []
		var mesh_frame := skeleton.global_transform.affine_inverse() * instance.global_transform
		for bind in range(skin.get_bind_count()):
			var bone := skeleton.find_bone(skin.get_bind_name(bind)) if not skin.get_bind_name(bind).is_empty() else skin.get_bind_bone(bind)
			matrices.append(skeleton.global_transform * skeleton.get_bone_global_pose(bone) * skin.get_bind_pose(bind) * mesh_frame)
			names.append(String(skeleton.get_bone_name(bone)))
		for surface in range(instance.mesh.get_surface_count()):
			var arrays := instance.mesh.surface_get_arrays(surface)
			var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			var bones := arrays[Mesh.ARRAY_BONES] as PackedInt32Array
			var weights := arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array
			var stride := 8 if instance.mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS else 4
			for vertex in range(vertices.size()):
				var point := Vector3.ZERO
				var tail_weight := 0.0
				var dominant := ""
				var weight := 0.0
				for influence in range(stride):
					var index := vertex * stride + influence
					var bind := bones[index]
					point += (matrices[bind] * vertices[vertex]) * weights[index]
					if "tail" in names[bind].to_lower(): tail_weight += weights[index]
					if weights[index] > weight:
						weight = weights[index]
						dominant = names[bind]
				if tail_weight >= 0.5 or "tail" in dominant.to_lower(): continue
				query.position = frame_delta * point
				for hit: Dictionary in space.intersect_point(query, 8):
					var body := hit["collider"] as Node
					if not body is PhysicsBody3D: continue
					var key := dominant + " / " + String(body.get_meta("source_node", body.name))
					result[key] = int(result.get(key, 0)) + 1
	return result
