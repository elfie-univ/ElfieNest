extends RefCounted
## Exact CPU skinning with immutable mesh inputs compiled once per actor.
## Packed-array transforms avoid rereading GPU surfaces and classifying vertices
## on every pose. No vertices, influences or physical body regions are removed.
var entries: Array[Dictionary] = []
var build_count := 0

func build(actor: ElfieActor, classify: Callable, budgeted: bool = false) -> void:
	entries.clear()
	build_count += 1
	var slice_started := Time.get_ticks_usec()
	# At low render rates, an unconditional 8 ms slice spends most preparation
	# waiting for costly frames. Keep interactive slices bounded at 8–32 ms.
	var budget_us := clampi(int(100000.0/maxf(Engine.get_frames_per_second(),1.0)),8000,32000)
	var skeleton := actor._furniture_hips().skeleton as Skeleton3D
	for mesh: MeshInstance3D in actor.find_children("*","MeshInstance3D",true,false):
		if mesh.skin == null or mesh.mesh == null: continue
		var frame := skeleton.global_transform.affine_inverse()*mesh.global_transform
		var bones := PackedInt32Array()
		var bind_frames: Array[Transform3D] = []
		var names: Array[String] = []
		var batches: Array[Dictionary] = []
		for bind in range(mesh.skin.get_bind_count()):
			var bone := skeleton.find_bone(mesh.skin.get_bind_name(bind)) if not mesh.skin.get_bind_name(bind).is_empty() else mesh.skin.get_bind_bone(bind)
			bones.append(bone)
			bind_frames.append(mesh.skin.get_bind_pose(bind)*frame)
			names.append(str(skeleton.get_bone_name(bone)))
			batches.append({"ids":[],"points":[],"weights":[]})
		var groups := {}
		var hull_groups := {}
		var count := 0
		var source_count := 0
		var identical := {}
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var stride := 8 if mesh.mesh.surface_get_format(surface)&Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS else 4
			var vertex_bytes := vertices.to_byte_array()
			var joint_bytes := joints.to_byte_array()
			var weight_bytes := weights.to_byte_array()
			for vertex in range(vertices.size()):
				# Seam duplicates can share evaluation only when every position,
				# joint index and weight is identical. Original region order remains.
				var key := vertex_bytes.slice(vertex*12,(vertex+1)*12)
				key.append_array(joint_bytes.slice(vertex*stride*4,(vertex+1)*stride*4))
				key.append_array(weight_bytes.slice(vertex*stride*4,(vertex+1)*stride*4))
				if identical.has(key):
					var alias: Dictionary = identical[key]
					groups[alias.region].append(alias.id)
				else:
					var dominant := ""
					var largest := 0.0
					var tail := 0.0
					for influence in range(stride):
						var at := vertex*stride+influence
						var weight := weights[at]
						if weight == 0.0: continue
						var bind := joints[at]
						if "tail" in names[bind].to_lower(): tail += weight
						if weight > largest: largest = weight; dominant = names[bind]
						var batch: Dictionary = batches[bind]
						batch.ids.append(count)
						batch.points.append((bind_frames[bind]*vertices[vertex])*weight)
						batch.weights.append(weight)
					var is_tail := tail >= 0.5 or "tail" in dominant.to_lower()
					var region := "tail/"+dominant if is_tail else str(classify.call(dominant))
					if region.ends_with("_lower_leg_foot"):
						region = dominant.trim_suffix("ToeBase").trim_suffix("Foot")+"_foot" if "Foot" in dominant or "Toe" in dominant else dominant
					if not groups.has(region):
						groups[region] = []
						hull_groups[region] = []
					hull_groups[region].append(count)
					groups[region].append(count)
					identical[key] = {"id":count,"region":region}
					count += 1
				source_count += 1
				if budgeted and source_count % 1024 == 0 and Time.get_ticks_usec()-slice_started >= budget_us:
					await actor.get_tree().process_frame
					slice_started = Time.get_ticks_usec()
					if not is_instance_valid(actor) or not actor.cycle_available():
						entries.clear()
						return
		for batch: Dictionary in batches:
			batch.ids = PackedInt32Array(batch.ids)
			batch.points = PackedVector3Array(batch.points)
			batch.weights = PackedFloat32Array(batch.weights)
		for key: String in groups:
			hull_groups[key] = PackedInt32Array(hull_groups[key])
			groups[key] = PackedInt32Array(groups[key])
		entries.append({"mesh":mesh,"resource":mesh.mesh,"skin":mesh.skin,"frame":frame,"bones":bones,"batches":batches,"groups":groups,"hull_groups":hull_groups,"count":count,"source_count":source_count})

func valid(actor: ElfieActor) -> bool:
	var skeleton := actor._furniture_hips().skeleton as Skeleton3D
	var meshes := 0
	for mesh: MeshInstance3D in actor.find_children("*","MeshInstance3D",true,false):
		if mesh.skin != null and mesh.mesh != null: meshes += 1
	if meshes != entries.size(): return false
	for entry: Dictionary in entries:
		if not is_instance_valid(entry.mesh) or entry.mesh.mesh != entry.resource or entry.mesh.skin != entry.skin: return false
		if not (skeleton.global_transform.affine_inverse()*entry.mesh.global_transform).is_equal_approx(entry.frame): return false
	return true

func sample(actor: ElfieActor, unique_only: bool = false) -> Dictionary:
	var skeleton := actor._furniture_hips().skeleton as Skeleton3D
	skeleton.force_update_all_bone_transforms()
	var root := actor.global_transform.affine_inverse()*skeleton.global_transform
	var result := {}
	for entry: Dictionary in entries:
		var points := PackedVector3Array()
		points.resize(entry.count)
		for bind in range(entry.batches.size()):
			var batch: Dictionary = entry.batches[bind]
			var ids: PackedInt32Array = batch.ids
			if ids.is_empty(): continue
			var bone := root*skeleton.get_bone_global_pose(entry.bones[bind])
			var transformed: PackedVector3Array = Transform3D(bone.basis,Vector3.ZERO)*(batch.points as PackedVector3Array)
			var weights: PackedFloat32Array = batch.weights
			for index in range(ids.size()): points[ids[index]] += transformed[index]+bone.origin*weights[index]
		var regions: Dictionary = entry.hull_groups if unique_only else entry.groups
		for key: String in regions:
			var ids: PackedInt32Array = regions[key]
			var selected := PackedVector3Array()
			selected.resize(ids.size())
			for index in range(ids.size()): selected[index] = points[ids[index]]
			if not result.has(key): result[key] = PackedVector3Array()
			var output: PackedVector3Array = result[key]
			output.append_array(selected)
			result[key] = output
	return result
