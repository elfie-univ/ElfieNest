extends SceneTree

const BINDING := preload("res://nest/assembly/glb_placement.gd")
const LIBRARY := "res://nest/courtyard/parts/shared/shore-stones.glb"
const INDEX := "res://nest/assembly/asset-index.json"

func _initialize() -> void:
	call_deferred("run")

static func verify(tree: SceneTree, bounds: Dictionary = {}) -> Dictionary:
	var library := (load(LIBRARY) as PackedScene).instantiate() as Node3D
	var shape := PackedByteArray()
	var colors := {}
	var result := {"error":"", "source_references":0, "instances":0, "visible_instances":0, "world_surface_displacement_bound_m":0.0}
	for i: int in 6:
		var node := library.find_child("part_%05d" % i, true, false) as MeshInstance3D
		if node == null or node.mesh == null:
			library.free()
			return {"error":"A round-stone variant is missing"}
		var arrays := var_to_bytes(node.mesh.surface_get_arrays(0))
		if i == 0: shape = arrays
		elif arrays != shape:
			library.free()
			return {"error":"Round stones still use different geometry"}
		var material := node.get_active_material(0) as StandardMaterial3D
		if material == null:
			library.free()
			return {"error":"A stone color was lost"}
		colors[material.albedo_color] = true
	library.free()
	if colors.size() != 3: return {"error":"Round stones must retain their three colors"}
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(INDEX))
	for consumer: Dictionary in index.fileGraph.entries["source:shore-stones"].usedBy:
		var path := "res://nest/" + str(index.fileGraph.entries[consumer.id].file)
		var scene := (load(path) as PackedScene).instantiate() as Node3D
		tree.root.add_child(scene)
		for binding: Node in scene.find_children("*", "Node3D", true, false):
			if binding.get_script() != BINDING or binding.library.resource_path != LIBRARY: continue
			for slot: int in binding.source_nodes.size():
				var node := binding.get_child(slot) as GeometryInstance3D
				var source := str(binding.source_nodes[slot])
				var local_bound := float(bounds.get(source, 0.0))
				var poses: Array[Transform3D] = []
				if node is MeshInstance3D and node.mesh != null:
					poses.append(node.global_transform)
				elif node is MultiMeshInstance3D and node.multimesh != null and node.multimesh.mesh != null:
					for i: int in node.multimesh.instance_count:
						poses.append(node.global_transform * node.multimesh.get_instance_transform(i))
				else:
					scene.free()
					return {"error":"An assembled stone lost its source mesh"}
				result.source_references += 1
				result.instances += poses.size()
				if not node.is_visible_in_tree(): continue
				result.visible_instances += poses.size()
				for pose: Transform3D in poses:
					var norm := sqrt(pose.basis.x.length_squared() + pose.basis.y.length_squared() + pose.basis.z.length_squared())
					result.world_surface_displacement_bound_m = maxf(result.world_surface_displacement_bound_m, local_bound * norm)
		scene.free()
	if result.source_references != 101: return {"error":"A stone placement or batch reference was lost"}
	return result

func run() -> void:
	var result := verify(self)
	if not str(result.error).is_empty():
		push_error(result.error)
		quit(1)
		return
	print("STONE_VARIANTS_AND_ALL_101_SCENE_REFERENCES_OK")
	quit(0)
