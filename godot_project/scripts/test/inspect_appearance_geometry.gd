extends SceneTree

## Development-only geometry inspection for appearance region discovery.
##
## This script reads the imported GLB scenes and prints mesh bounds, node
## transforms, and skeleton bones. It does not alter scenes, meshes, materials,
## or the production appearance path.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")


func _init() -> void:
	call_deferred("_inspect")


func _inspect() -> void:
	await _inspect_species("dog", DOG_SCENE)
	await _inspect_species("fox", FOX_SCENE)
	quit()


func _inspect_species(species_id: String, scene: PackedScene) -> void:
	var actor := scene.instantiate() as Node3D
	root.add_child(actor)
	await process_frame
	await process_frame
	await process_frame
	print("REGION_GEOMETRY_BEGIN species=%s" % species_id)
	var skeleton: Skeleton3D = null
	for node in actor.find_children("*", "Skeleton3D", true, false):
		var candidate := node as Skeleton3D
		if candidate != null:
			skeleton = candidate
			break
	for node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var local_bounds := mesh_instance.get_aabb()
		print(
			"MESH name=%s path=%s node_scale=%s global_scale=%s global_origin=%s mesh_min=%s mesh_max=%s node_aabb_min=%s node_aabb_max=%s surfaces=%d"
			% [
				mesh_instance.name,
				str(actor.get_path_to(mesh_instance)),
				str(mesh_instance.scale),
				str(mesh_instance.global_transform.basis.get_scale()),
				str(mesh_instance.global_position),
				str(mesh_instance.mesh.get_aabb().position),
				str(mesh_instance.mesh.get_aabb().end),
				str(local_bounds.position),
				str(local_bounds.end),
				mesh_instance.mesh.get_surface_count(),
			]
		)
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var arrays: Array = mesh_instance.mesh.surface_get_arrays(surface_index)
			var vertices = arrays[Mesh.ARRAY_VERTEX]
			var bone_ids = arrays[Mesh.ARRAY_BONES]
			var bone_weights = arrays[Mesh.ARRAY_WEIGHTS]
			if vertices == null or bone_ids == null or bone_weights == null or bone_ids.size() == 0:
				continue
			var counts: Dictionary = {}
			var min_x: Dictionary = {}
			var max_x: Dictionary = {}
			var min_y: Dictionary = {}
			var max_y: Dictionary = {}
			var min_z: Dictionary = {}
			var max_z: Dictionary = {}
			var head_id := 23 if species_id == "dog" else 27
			var top_head_count := 0
			var top_head_min_z := 999.0
			var top_head_max_z := -999.0
			var top_head_min_x := 999.0
			var top_head_max_x := -999.0
			var core_head_count := 0
			var core_head_min_y := 999.0
			var core_head_max_y := -999.0
			var vertex_count := int(bone_ids.size() / 4)
			for vertex_index in range(vertex_count):
				var base := vertex_index * 4
				var vertex: Vector3 = vertices[vertex_index]
				for slot in range(4):
					var weight := float(bone_weights[base + slot])
					if weight <= 0.05:
						continue
					var bone_id := int(bone_ids[base + slot])
					counts[bone_id] = int(counts.get(bone_id, 0)) + 1
					if bone_id == head_id and weight >= 0.20 and vertex.y >= 1.65:
						top_head_count += 1
						top_head_min_z = min(top_head_min_z, vertex.z)
						top_head_max_z = max(top_head_max_z, vertex.z)
						top_head_min_x = min(top_head_min_x, vertex.x)
						top_head_max_x = max(top_head_max_x, vertex.x)
					var core_z_min := 0.10 if species_id == "dog" else 0.25
					if (
						bone_id == head_id
						and weight >= 0.20
						and abs(vertex.x) <= 0.14
						and vertex.z >= core_z_min
					):
						core_head_count += 1
						core_head_min_y = min(core_head_min_y, vertex.y)
						core_head_max_y = max(core_head_max_y, vertex.y)
					if not min_x.has(bone_id):
						min_x[bone_id] = vertex.x
						max_x[bone_id] = vertex.x
						min_y[bone_id] = vertex.y
						max_y[bone_id] = vertex.y
						min_z[bone_id] = vertex.z
						max_z[bone_id] = vertex.z
					else:
						min_x[bone_id] = min(float(min_x[bone_id]), vertex.x)
						max_x[bone_id] = max(float(max_x[bone_id]), vertex.x)
						min_y[bone_id] = min(float(min_y[bone_id]), vertex.y)
						max_y[bone_id] = max(float(max_y[bone_id]), vertex.y)
						min_z[bone_id] = min(float(min_z[bone_id]), vertex.z)
						max_z[bone_id] = max(float(max_z[bone_id]), vertex.z)
			var sorted_ids: Array = counts.keys()
			sorted_ids.sort()
			var bone_summary: Array[String] = []
			for bone_id in sorted_ids:
				var bone_name := "unknown"
				if skeleton != null and bone_id >= 0 and bone_id < skeleton.get_bone_count():
					bone_name = skeleton.get_bone_name(bone_id)
				bone_summary.append(
					"%d:%s:%d:x(%.1f,%.1f):y(%.1f,%.1f):z(%.1f,%.1f)"
					% [
						bone_id,
						bone_name,
						int(counts[bone_id]),
						float(min_x[bone_id]),
						float(max_x[bone_id]),
						float(min_y[bone_id]),
						float(max_y[bone_id]),
						float(min_z[bone_id]),
						float(max_z[bone_id]),
					]
				)
			print(
				"WEIGHTS surface=%d vertices=%d slots=%d ids=%s"
				% [surface_index, vertex_count, bone_ids.size(), ",".join(bone_summary)]
			)
			print(
				"HEAD_TOP_CANDIDATE head_id=%d count=%d x(%.3f,%.3f) z(%.3f,%.3f)"
				% [head_id, top_head_count, top_head_min_x, top_head_max_x, top_head_min_z, top_head_max_z]
			)
			print(
				"HEAD_CORE_CANDIDATE head_id=%d count=%d y(%.3f,%.3f)"
				% [head_id, core_head_count, core_head_min_y, core_head_max_y]
			)
	for node in actor.find_children("*", "Skeleton3D", true, false):
		var skeleton_node := node as Skeleton3D
		if skeleton_node == null:
			continue
		print("SKELETON path=%s bones=%d" % [str(actor.get_path_to(skeleton_node)), skeleton_node.get_bone_count()])
		for bone_index in range(skeleton_node.get_bone_count()):
			print(
				"BONE index=%d name=%s parent=%d rest_origin=%s"
				% [
					bone_index,
					skeleton_node.get_bone_name(bone_index),
					skeleton_node.get_bone_parent(bone_index),
					str(skeleton_node.get_bone_rest(bone_index).origin),
				]
			)
	print("REGION_GEOMETRY_END species=%s" % species_id)
	actor.queue_free()
	await process_frame
