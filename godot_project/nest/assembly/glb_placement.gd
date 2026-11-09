@tool
extends Node3D
## Bind imported GLB meshes to individual placements and instance batches.

@export var library: PackedScene
@export_storage var source_nodes: PackedStringArray
@export_storage var material_variants: Dictionary
@export_storage var instance_batches: Dictionary

static var cached_libraries: Dictionary = {}

func _ready() -> void:
	if library != null and not library.changed.is_connected(library_changed):
		library.changed.connect(library_changed)
	if not bind_meshes():
		push_error("Cannot resolve GLB placements: " + str(get_path()))

func library_changed() -> void:
	if library == null: return
	cached_libraries.erase(library.resource_path)
	call_deferred("bind_meshes")

func bind_meshes() -> bool:
	if library == null or source_nodes.size() != get_child_count():
		return false
	var path := library.resource_path
	var modified := FileAccess.get_modified_time(path)
	if not cached_libraries.has(path) or cached_libraries[path].modified != modified:
		var imported := import_meshes(path)
		if imported.is_empty(): return false
		cached_libraries[path] = {"modified": modified, "meshes": imported}
	var meshes: Dictionary = cached_libraries[path].meshes
	var context := get_parent()
	while context != null and not context.has_meta("estate_module"):
		context = context.get_parent()
	var module := str(context.get_meta("estate_module")) if context != null else ""
	for index: int in source_nodes.size():
		var target := get_child(index)
		var mesh := select_mesh(meshes, source_nodes[index], str(target.get_meta("v044_path", "")), module)
		if mesh == null:
			push_error("Missing GLB node %s in %s" % [source_nodes[index], path])
			return false
		if target is MeshInstance3D:
			target.mesh = mesh
			var materials: Array = material_variants.get(index, [])
			for surface: int in materials.size():
				target.set_surface_override_material(surface, materials[surface])
		elif target is MultiMeshInstance3D and instance_batches.has(index):
			var data: Dictionary = instance_batches[index]
			var buffer: PackedFloat32Array = data.buffer
			if data.transform_format not in [MultiMesh.TRANSFORM_2D, MultiMesh.TRANSFORM_3D]: return false
			var stride := 12 if data.transform_format == MultiMesh.TRANSFORM_3D else 8
			if data.use_colors: stride += 4
			if data.use_custom_data: stride += 4
			if data.instance_count < 0 or buffer.size() != data.instance_count * stride: return false
			var batch := MultiMesh.new()
			batch.transform_format = data.transform_format
			batch.use_colors = data.use_colors
			batch.use_custom_data = data.use_custom_data
			batch.mesh = mesh
			batch.instance_count = data.instance_count
			batch.visible_instance_count = data.visible_instance_count
			batch.custom_aabb = data.custom_aabb
			if not buffer.is_empty():
				# Compatibility packs custom/color values to 16 bits. Validate the
				# canonical input above; GPU readback is not a source-data checksum.
				batch.buffer = buffer
			target.multimesh = batch
		else:
			return false
		if context != null:
			var ordinal := int(module.trim_prefix("M"))
			if ordinal >= 1 and ordinal <= 8 and target.layers & (1 << 8):
				target.layers = (target.layers & ~(1 << 8)) | (1 << (7 + ordinal))
		if target is MeshInstance3D and mesh.has_meta("nest_render_partition"):
			rebuild_render_partition(target)
			var changed := queue_render_partition.bind(target)
			if not mesh.changed.is_connected(changed): mesh.changed.connect(changed)
	return true

func import_meshes(_path: String) -> Dictionary:
	var model := library.instantiate()
	var meshes := {}
	for node: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		if node.mesh != null:
			if not restore_materials(node):
				model.free()
				return {}
			var extras: Dictionary = node.get_meta("extras", {})
			node.mesh.set_meta("nest_source_extras", extras.duplicate(true))
			node.mesh.set_meta("nest_source_library", library.resource_path)
			if extras.has("nest_normal_variants"):
				node.mesh.set_meta("nest_normal_variants", extras.nest_normal_variants)
			if extras.has("nest_render_partition"):
				node.mesh.set_meta("nest_render_partition", extras.nest_render_partition)
			meshes[str(node.name)] = node.mesh
	model.free()
	return meshes

static func select_mesh(meshes: Dictionary, source: String, placement: String, module: String) -> Mesh:
	var mesh: Mesh = meshes.get(source)
	if mesh == null: return null
	var variants: Dictionary = mesh.get_meta("nest_normal_variants", {})
	var room: Dictionary = variants.get(module, {})
	return meshes.get(str(room[placement])) if room.has(placement) else mesh

static func restore_materials(node: MeshInstance3D) -> bool:
	# glTF cannot express every native material setting. Keep the small set of
	# native differences with its owning GLB, for placements and isolated review.
	var extras: Dictionary = node.get_meta("extras", {})
	var materials: Array = extras.get("nest_materials", [])
	if materials.is_empty(): return true
	if node.mesh == null or materials.size() != node.mesh.get_surface_count(): return false
	for surface: int in materials.size():
		var values: Dictionary = materials[surface]
		if values.is_empty(): continue
		var imported := node.mesh.surface_get_material(surface) as StandardMaterial3D
		if imported == null: return false
		var restored := imported.duplicate() as StandardMaterial3D
		for property: String in values:
			if property not in ["emission", "albedo_color", "texture_repeat", "emission_operator", "depth_draw_mode", "metallic_specular", "transparency"]: return false
			var data: Variant = values[property]
			if property in ["emission", "albedo_color"]:
				if not data is Array or data.size() != 4: return false
				data = Color(data[0],data[1],data[2],data[3])
			restored.set(property, data)
		node.mesh.surface_set_material(surface, restored)
	return true

func queue_render_partition(source: MeshInstance3D) -> void:
	call_deferred("rebuild_render_partition", source)

func rebuild_render_partition(source: MeshInstance3D) -> void:
	if not is_instance_valid(source) or source.mesh == null: return
	var options: Dictionary = source.mesh.get_meta("nest_render_partition", {})
	if options.is_empty(): return
	var cell_size := float(options.cell_size)
	assert(cell_size > 0.0)
	var signature := hash(var_to_bytes([source.mesh.get("_surfaces"), options, source.global_transform]))
	var previous := source.get_node_or_null("RenderChunks")
	if previous != null and previous.get_meta("source_signature") == signature: return
	if previous != null:
		source.remove_child(previous)
		previous.free()
	var chunks := Node3D.new()
	chunks.name = "RenderChunks"
	chunks.set_meta("source_signature", signature)
	source.add_child(chunks)
	# Owner stays null: these meshes are disposable, never saved into an SCN.
	var layers := int(source.get_meta("source_render_layers", source.layers))
	source.set_meta("source_render_layers", layers)
	for chunk: MeshInstance3D in partition_mesh(source, cell_size):
		chunks.add_child(chunk)
		for property: String in ["cast_shadow", "transparency", "extra_cull_margin", "ignore_occlusion_culling", "gi_mode", "lod_bias", "sorting_offset", "sorting_use_aabb_center", "visibility_range_begin", "visibility_range_end", "visibility_range_begin_margin", "visibility_range_end_margin", "visibility_range_fade_mode"]:
			chunk.set(property, source.get(property))
		var surface := int(chunk.get_meta("source_surface"))
		chunk.layers = int(options.get("surface_layers", [])[surface]) if options.has("surface_layers") else layers
		chunk.custom_aabb = (chunk.mesh as ArrayMesh).custom_aabb
		chunk.set_meta("v044_path", str(source.get_meta("v044_path", source.name)) + "/" + str(chunk.name))
		chunk.set_meta("source_geometry_path", str(source.get_meta("v044_path", source.name)))
	# Disabling only the original draw preserves child visibility and geometry ownership.
	source.layers = 0

static func partition_mesh(source: MeshInstance3D, cell_size: float = 8.0) -> Array[MeshInstance3D]:
	assert(cell_size > 0.0 and source.mesh is ArrayMesh)
	var result: Array[MeshInstance3D] = []
	for surface: int in source.mesh.get_surface_count():
		var arrays := source.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
		var cells := {}
		var count := vertices.size() if indices.is_empty() else indices.size()
		for i: int in range(0, count, 3):
			var triangle := PackedInt32Array()
			var center := Vector3.ZERO
			for j: int in range(3):
				var index: int = i + j if indices.is_empty() else indices[i + j]
				triangle.append(index)
				center += source.global_transform * vertices[index] / 3.0
			var cell := Vector2i(floori(center.x / cell_size), floori(center.z / cell_size))
			var bucket: PackedInt32Array = cells.get(cell, PackedInt32Array())
			bucket.append_array(triangle)
			cells[cell] = bucket
		for cell: Vector2i in cells:
			var selected := PackedInt32Array()
			var remapped := PackedInt32Array()
			var mapping := {}
			for old: int in cells[cell]:
				if not mapping.has(old):
					mapping[old] = selected.size()
					selected.append(old)
				remapped.append(mapping[old])
			var chunk := MeshInstance3D.new()
			chunk.name = "Chunk_%d_%d_%d" % [surface, cell.x, cell.y]
			chunk.mesh = packed_subset(source.mesh, surface, selected, remapped, vertices)
			chunk.mesh.surface_set_material(0, source.get_active_material(surface))
			chunk.set_meta("source_surface", surface)
			chunk.set_meta("source_indices", cells[cell])
			result.append(chunk)
	return result

static func packed_subset(original: ArrayMesh, surface: int, selected: PackedInt32Array, indices: PackedInt32Array, vertices: PackedVector3Array) -> ArrayMesh:
	# Keep native packed attributes unchanged, including normal quantization.
	var source: Dictionary = (original.get("_surfaces") as Array)[surface]
	assert((source.get("skin_data", PackedByteArray()) as PackedByteArray).is_empty())
	var output := source.duplicate()
	var format: int = source.format
	var count: int = source.vertex_count
	var position_stride := RenderingServer.mesh_surface_get_format_vertex_stride(format, count)
	var normal_stride := RenderingServer.mesh_surface_get_format_normal_tangent_stride(format, count)
	var normal_offset := RenderingServer.mesh_surface_get_format_offset(format, count, Mesh.ARRAY_NORMAL)
	var data: PackedByteArray = source.vertex_data
	var packed := PackedByteArray()
	for index: int in selected: packed.append_array(data.slice(index * position_stride, (index + 1) * position_stride))
	if normal_stride > 0:
		for index: int in selected: packed.append_array(data.slice(normal_offset + index * normal_stride, normal_offset + (index + 1) * normal_stride))
	output.vertex_data = packed
	var attributes: PackedByteArray = source.get("attribute_data", PackedByteArray())
	var stride := RenderingServer.mesh_surface_get_format_attribute_stride(format, count)
	var packed_attributes := PackedByteArray()
	for index: int in selected: packed_attributes.append_array(attributes.slice(index * stride, (index + 1) * stride))
	output.attribute_data = packed_attributes
	var index_stride := 2 if selected.size() <= 65536 else 4
	var index_bytes := PackedByteArray()
	index_bytes.resize(indices.size() * index_stride)
	for i: int in indices.size():
		if index_stride == 2: index_bytes.encode_u16(i * 2, indices[i])
		else: index_bytes.encode_u32(i * 4, indices[i])
	output.index_data = index_bytes
	output.index_count = indices.size()
	output.vertex_count = selected.size()
	output.format = format | Mesh.ARRAY_FORMAT_INDEX
	output.lods = []
	var result := ArrayMesh.new()
	result.set("_surfaces", [output])
	var bounds := AABB(vertices[selected[0]], Vector3.ZERO)
	for index: int in selected: bounds = bounds.expand(vertices[index])
	result.custom_aabb = bounds
	return result
