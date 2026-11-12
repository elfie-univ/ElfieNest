@tool
extends RefCounted
## Batch standard glTF child instances while keeping their owning component selectable.

static func relative_transform(node: Node3D, ancestor: Node3D) -> Transform3D:
	var result := node.transform
	var parent := node.get_parent() as Node3D
	while parent != ancestor:
		result = parent.transform * result
		parent = parent.get_parent() as Node3D
	return result

static func collect(source: Node3D) -> Array[Dictionary]:
	var groups: Array[Dictionary] = []
	var slots := {}
	for node: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == null: continue
		var surface := int(node.get_meta("extras", {}).get("nest_surface", 0))
		var key := str(node.mesh.get_instance_id()) + ":" + str(surface)
		if not slots.has(key):
			slots[key] = groups.size()
			var mesh := node.mesh
			if node.get_surface_override_material(0) != null:
				mesh = mesh.duplicate()
				mesh.surface_set_material(0, node.get_surface_override_material(0))
			groups.append({"mesh": mesh, "surface": surface, "transforms": []})
		groups[slots[key]].transforms.append(relative_transform(node, source))
	return groups

static func populate(target: Node3D, groups: Array, variants: Array = []) -> void:
	var old := target.get_node_or_null("SharedLeafInstances")
	if old != null: old.free()
	var container := Node3D.new()
	container.name = "SharedLeafInstances"
	target.add_child(container)
	var geometry := target as GeometryInstance3D
	var source_path := str(target.get_meta("v044_path", target.get_meta("extras", {}).get("v044_path", "")))
	for group: Dictionary in groups:
		var batch := MultiMesh.new()
		batch.transform_format = MultiMesh.TRANSFORM_3D
		batch.mesh = group.mesh
		batch.instance_count = group.transforms.size()
		var buffer := PackedFloat32Array()
		for transform: Transform3D in group.transforms:
			buffer.append_array(PackedFloat32Array([
				transform.basis.x.x, transform.basis.y.x, transform.basis.z.x, transform.origin.x,
				transform.basis.x.y, transform.basis.y.y, transform.basis.z.y, transform.origin.y,
				transform.basis.x.z, transform.basis.y.z, transform.basis.z.z, transform.origin.z,
			]))
		batch.buffer = buffer
		batch.set_meta("nest_instance_buffer", buffer)
		var instance := MultiMeshInstance3D.new()
		instance.multimesh = batch
		if geometry != null:
			instance.layers = geometry.layers
			instance.cast_shadow = geometry.cast_shadow
		if group.surface < variants.size(): instance.material_override = variants[group.surface]
		instance.set_meta("nest_instance_owner", target.get_instance_id())
		instance.set_meta("source_geometry_path", source_path)
		container.add_child(instance)

static func prepare_preview(source: Node3D) -> void:
	var groups := collect(source)
	for child: Node in source.get_children(): child.free()
	populate(source, groups)
