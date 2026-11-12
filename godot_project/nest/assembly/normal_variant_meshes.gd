@tool
extends RefCounted
## Reuse identical native geometry; keep the exact per-placement shading data.

static func restore(base: ArrayMesh, delta: Dictionary) -> ArrayMesh:
	var mesh := base.duplicate(false) as ArrayMesh
	mesh.clear_surfaces()
	var surfaces: Array = base.get("_surfaces")
	var restored := []
	for i: int in surfaces.size():
		var surface: Dictionary = surfaces[i].duplicate()
		var changes: Dictionary = delta.surfaces[i]
		for key: Variant in changes:
			if key == "normal_data":
				var offset := RenderingServer.mesh_surface_get_format_offset(surface.format, surface.vertex_count, Mesh.ARRAY_NORMAL)
				var packed: PackedByteArray = surface.vertex_data.slice(0, offset)
				packed.append_array(changes.normal_data)
				surface.vertex_data = packed
			else:
				surface[key] = changes[key]
		restored.append(surface)
	mesh.set("_surfaces", restored)
	if delta.has("shadow"):
		mesh.shadow_mesh = restore(base.shadow_mesh, delta.shadow)
	mesh.resource_name = delta.name
	return mesh
