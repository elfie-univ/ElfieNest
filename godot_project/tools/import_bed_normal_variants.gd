@tool
extends EditorScenePostImport
## Store native differences against the base shape without re-encoding attributes.

func _post_import(scene: Node) -> Object:
	var nodes := {}
	for node: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		nodes[str(node.name)] = node
	var count := 0
	for name: String in nodes:
		var node: MeshInstance3D = nodes[name]
		var extras: Dictionary = node.get_meta("extras", {})
		if not extras.has("normal_variant_of"): continue
		var base: MeshInstance3D = nodes[extras.normal_variant_of]
		var delta := difference(base.mesh, node.mesh)
		# A changed schema is an import error, never permission to discard data.
		if delta.is_empty():
			push_error("Cannot share bed normal variant " + name)
			return null
		node.set_meta("nest_normal_delta", delta)
		node.mesh = base.mesh
		count += 1
	print("BED_NORMAL_SHARING variants=", count)
	return scene

func difference(base: ArrayMesh, variant: ArrayMesh) -> Dictionary:
	if base.get_blend_shape_count() != 0 or variant.get_blend_shape_count() != 0: return {}
	if base.custom_aabb != variant.custom_aabb or base.lightmap_size_hint != variant.lightmap_size_hint: return {}
	if (base.shadow_mesh == null) != (variant.shadow_mesh == null): return {}
	var sources: Array = base.get("_surfaces")
	var targets: Array = variant.get("_surfaces")
	if sources.size() != targets.size(): return {}
	var changes := []
	for i: int in sources.size():
		var source: Dictionary = sources[i]; var target: Dictionary = targets[i]
		if source.keys() != target.keys(): return {}
		var changed := {}
		for key: Variant in target:
			if var_to_bytes(source[key]) == var_to_bytes(target[key]): continue
			if key == "vertex_data" and source.format == target.format and source.vertex_count == target.vertex_count:
				var offset := RenderingServer.mesh_surface_get_format_offset(source.format, source.vertex_count, Mesh.ARRAY_NORMAL)
				if offset > 0 and source.vertex_data.slice(0, offset) == target.vertex_data.slice(0, offset):
					changed.normal_data = target.vertex_data.slice(offset)
					continue
			changed[key] = target[key]
		changes.append(changed)
	var result := {"surfaces": changes, "name": variant.resource_name}
	if variant.shadow_mesh != null:
		var shadow := difference(base.shadow_mesh, variant.shadow_mesh)
		if shadow.is_empty(): return {}
		result.shadow = shadow
	return result
