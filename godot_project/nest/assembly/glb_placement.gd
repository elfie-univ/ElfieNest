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
	for index: int in source_nodes.size():
		var target := get_child(index)
		var mesh: Mesh = meshes.get(source_nodes[index])
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
	return true

func import_meshes(_path: String) -> Dictionary:
	var model := library.instantiate()
	var meshes := {}
	for node: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		if node.mesh != null:
			meshes[str(node.name)] = node.mesh
	model.free()
	return meshes
