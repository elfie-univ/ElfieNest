@tool
extends Node3D
## Bind imported GLB meshes to individual placements and instance batches.

@export var library: PackedScene
@export_storage var source_nodes: PackedStringArray
@export_storage var material_variants: Dictionary
@export_storage var instance_batches: Dictionary

static var cached_libraries: Dictionary = {}

func _ready() -> void:
	if not bind_meshes():
		push_error("Cannot resolve GLB placements: " + str(get_path()))

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
			var batch := MultiMesh.new()
			batch.transform_format = data.transform_format
			batch.use_colors = data.use_colors
			batch.use_custom_data = data.use_custom_data
			batch.mesh = mesh
			batch.instance_count = data.instance_count
			batch.visible_instance_count = data.visible_instance_count
			batch.custom_aabb = data.custom_aabb
			var buffer: PackedFloat32Array = data.buffer
			if not buffer.is_empty():
				batch.buffer = buffer
				if batch.buffer.to_byte_array() != buffer.to_byte_array(): return false
			target.multimesh = batch
		else:
			return false
		if context != null:
			var ordinal := int(module.trim_prefix("M"))
			if ordinal >= 1 and ordinal <= 8 and target.layers & (1 << 8):
				target.layers = (target.layers & ~(1 << 8)) | (1 << (7 + ordinal))
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
			if extras.has("nest_normal_variants"):
				node.mesh.set_meta("nest_normal_variants", extras.nest_normal_variants)
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
