extends Node3D
class_name CompleteEstateFinal

const INSTANCE_SIDECAR_PATH := "res://rooms/estate/ElfieNest-complete-final.instances.bin"
const SIDECAR_MAGIC := "ENINST01"
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const SURFACE := preload("res://rooms/estate/estate_surface.gd")
const WATER := preload("res://rooms/estate/estate_water.gd")
const MAX_BATCH_INSTANCES := 128
const BATCH_CELL_SIZE := 16.0

var multimesh_group_count := 0
var multimesh_instance_count := 0
var restore_error := ""
var _canopy_meshes: Dictionary = {}


func _ready() -> void:
	var outdoor := load("res://rooms/estate/estate_outdoor_lighting.scn") as PackedScene
	if outdoor == null:
		_fail_restore("Build the current estate lighting before loading the composed world")
		return
	var layout := outdoor.instantiate() as Node3D
	add_child(layout)
	_apply_outdoor_layout(layout)
	DAYLIGHT.apply(self)
	WATER.attach($CompleteFinal)
	_restore_instanced_groups()


func _apply_outdoor_layout(layout: Node3D) -> void:
	for mesh: MeshInstance3D in $CompleteFinal.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if str(extras.get("outdoor_fixture_id", "")).begins_with("R"):
			for light: Dictionary in extras.get("design_lights", []):
				light.merge({"intensity": PI, "distance": 14.0, "angle": deg_to_rad(78.0), "attenuation": 0.7, "angle_attenuation": 0.2}, true)
			mesh.set_meta("extras", extras)
	for patch: MeshInstance3D in layout.find_children("*", "MeshInstance3D", true, false):
		if not patch.has_meta("source_ground"):
			continue
		var original := $CompleteFinal.find_child(str(patch.get_meta("source_ground")), true, false) as MeshInstance3D
		assert(original != null, "Lighting patch lost its original ground surface")
		original.visible = false


func _restore_instanced_groups() -> void:
	var file := FileAccess.open(INSTANCE_SIDECAR_PATH, FileAccess.READ)
	if file == null:
		_fail_restore("Complete final instance sidecar could not be opened")
		return
	file.big_endian = false
	var magic := file.get_buffer(8).get_string_from_ascii()
	var version := file.get_32()
	var group_count := file.get_32()
	var expected_instance_count := file.get_32()
	if magic != SIDECAR_MAGIC or version != 1:
		file.close()
		_fail_restore("Complete final instance sidecar header is invalid")
		return

	var observed_instance_count := 0
	for _group_index in range(group_count):
		if file.get_length() - file.get_position() < 8:
			_fail_restore("Complete final instance sidecar group header is truncated")
			return
		var name_length := file.get_32()
		var instance_count := file.get_32()
		if (
			name_length == 0 or name_length > 256
			or instance_count > expected_instance_count - observed_instance_count
			or name_length + instance_count * 64 > file.get_length() - file.get_position()
		):
			_fail_restore("Complete final instance sidecar group size is invalid")
			return
		var group_name := file.get_buffer(name_length).get_string_from_utf8()
		var matrices := file.get_buffer(instance_count * 64).to_float32_array()
		var instance_buffer := PackedFloat32Array()
		instance_buffer.resize(instance_count * 12)
		for instance_index in range(instance_count):
			var matrix_index := instance_index * 16
			var buffer_index := instance_index * 12
			instance_buffer[buffer_index + 0] = matrices[matrix_index + 0]
			instance_buffer[buffer_index + 1] = matrices[matrix_index + 4]
			instance_buffer[buffer_index + 2] = matrices[matrix_index + 8]
			instance_buffer[buffer_index + 3] = matrices[matrix_index + 12]
			instance_buffer[buffer_index + 4] = matrices[matrix_index + 1]
			instance_buffer[buffer_index + 5] = matrices[matrix_index + 5]
			instance_buffer[buffer_index + 6] = matrices[matrix_index + 9]
			instance_buffer[buffer_index + 7] = matrices[matrix_index + 13]
			instance_buffer[buffer_index + 8] = matrices[matrix_index + 2]
			instance_buffer[buffer_index + 9] = matrices[matrix_index + 6]
			instance_buffer[buffer_index + 10] = matrices[matrix_index + 10]
			instance_buffer[buffer_index + 11] = matrices[matrix_index + 14]
		var marker := $CompleteFinal.find_child(group_name, true, false)
		if marker == null:
			file.close()
			_fail_restore("Complete final instance marker is missing: %s" % group_name)
			return
		var source_mesh := _first_mesh_instance(marker)
		if source_mesh == null or source_mesh.mesh == null:
			file.close()
			_fail_restore("Complete final instance marker has no mesh: %s" % group_name)
			return

		marker.visible = false
		var shared_mesh := _full_detail_canopy(source_mesh.mesh)
		for surface in range(shared_mesh.get_surface_count()):
			var override_material := source_mesh.get_surface_override_material(surface)
			if override_material != null:
				shared_mesh.surface_set_material(surface, override_material)
			if shared_mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR:
				var material := shared_mesh.surface_get_material(surface) as BaseMaterial3D
				if material != null:
					material.vertex_color_use_as_albedo = true
					if SURFACE.supports(material, true):
						shared_mesh.surface_set_material(surface, SURFACE.make_material(material, 0.0, 0.0, true))
		var batch_index := 0
		for batch: Dictionary in _spatial_batches(instance_buffer):
			var multimesh := MultiMesh.new()
			multimesh.transform_format = MultiMesh.TRANSFORM_3D
			multimesh.mesh = shared_mesh
			multimesh.instance_count = batch["source_indices"].size()
			multimesh.buffer = batch["buffer"]
			var multimesh_instance := MultiMeshInstance3D.new()
			multimesh_instance.name = "%s__MultiMesh_%d" % [group_name, batch_index]
			multimesh_instance.multimesh = multimesh
			# All sidecar groups are landscape. Room fixtures must not light an
			# entire forest just because its old all-site AABB touched a room.
			multimesh_instance.layers = 1 | DAYLIGHT.LANDSCAPE_LIGHT_LAYER
			multimesh_instance.material_override = source_mesh.material_override
			multimesh_instance.cast_shadow = source_mesh.cast_shadow
			multimesh_instance.set_meta("asset_role", "complete-final-instanced-group")
			multimesh_instance.set_meta("source_group", group_name)
			multimesh_instance.set_meta("source_instance_indices", batch["source_indices"])
			add_child(multimesh_instance)
			batch_index += 1
		observed_instance_count += instance_count

	var fully_consumed := file.get_position() == file.get_length()
	file.close()
	if observed_instance_count != expected_instance_count or not fully_consumed:
		_fail_restore(
			"Complete final instance count mismatch: observed=%d expected=%d"
			% [observed_instance_count, expected_instance_count]
		)
		return
	multimesh_group_count = group_count
	multimesh_instance_count = observed_instance_count
	print("ESTATE_RENDER_BATCHES source_groups=", group_count, " batches=", find_children("*", "MultiMeshInstance3D", false, false).size(), " instances=", observed_instance_count)


static func _spatial_batches(buffer: PackedFloat32Array) -> Array[Dictionary]:
	# Partition only transforms. Mesh buffers/materials remain shared and exact.
	# Compact bounds allow camera/light culling before vertex work is submitted.
	var cells: Dictionary = {}
	for index in range(buffer.size() / 12):
		var offset := index * 12
		var cell := Vector2i(floori(buffer[offset + 3] / BATCH_CELL_SIZE), floori(buffer[offset + 11] / BATCH_CELL_SIZE))
		if not cells.has(cell):
			cells[cell] = PackedInt32Array()
		var indices: PackedInt32Array = cells[cell]
		indices.append(index)
		cells[cell] = indices
	var batches: Array[Dictionary] = []
	for cell_indices: PackedInt32Array in cells.values():
		var indices := _spatial_order(cell_indices, buffer)
		for start in range(0, indices.size(), MAX_BATCH_INSTANCES):
			var batch_indices := indices.slice(start, mini(start + MAX_BATCH_INSTANCES, indices.size()))
			var batch_buffer := PackedFloat32Array()
			batch_buffer.resize(batch_indices.size() * 12)
			for index in range(batch_indices.size()):
				for component in range(12):
					batch_buffer[index * 12 + component] = buffer[batch_indices[index] * 12 + component]
			batches.append({"source_indices": batch_indices, "buffer": batch_buffer})
	return batches


static func _spread_spatial_bits(value: int) -> int:
	var bits := value & 0x3ff
	bits = (bits | (bits << 16)) & 0x030000ff
	bits = (bits | (bits << 8)) & 0x0300f00f
	bits = (bits | (bits << 4)) & 0x030c30c3
	return (bits | (bits << 2)) & 0x09249249


static func _spatial_order(indices: PackedInt32Array, buffer: PackedFloat32Array) -> PackedInt32Array:
	if indices.size() <= MAX_BATCH_INSTANCES:
		return indices
	# Morton order keeps neighbouring transforms together without adding draws.
	# Quantization only orders indices; every uploaded transform stays exact.
	var keys: Array[Vector2i] = []
	for index in indices:
		var offset := index * 12
		var x := floori(buffer[offset + 3] * 8.0) & 127
		var y := clampi(floori((buffer[offset + 7] + 16.0) * 8.0), 0, 1023)
		var z := floori(buffer[offset + 11] * 8.0) & 127
		var key := _spread_spatial_bits(x) | (_spread_spatial_bits(y) << 1) | (_spread_spatial_bits(z) << 2)
		keys.append(Vector2i(key, index))
	keys.sort()
	var ordered := PackedInt32Array()
	ordered.resize(indices.size())
	for i in range(keys.size()):
		ordered[i] = keys[i].y
	return ordered


static func is_canopy_mesh(mesh: Mesh) -> bool:
	if mesh.get_meta("full_detail_canopy", false):
		return true
	for surface in range(mesh.get_surface_count()):
		var material := mesh.surface_get_material(surface) as BaseMaterial3D
		if material == null:
			continue
		# The approved broadleaf crowns have unnamed, vertex-painted leaf
		# surfaces at roughness .78; named needle clusters form the other crowns.
		if material.resource_name == "Mixed deep green needles" or (
			bool(mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR)
			and is_equal_approx(material.roughness, 0.78)
		):
			return true
	return false


func _full_detail_canopy(mesh: Mesh) -> Mesh:
	if not mesh is ArrayMesh or not is_canopy_mesh(mesh):
		return mesh
	var identity := mesh.get_instance_id()
	if _canopy_meshes.has(identity):
		return _canopy_meshes[identity]
	# Reuse Godot's serialized surfaces, including their exact compressed
	# vertex, normal, color and base index buffers. Only automatic LOD index
	# alternatives are removed; rebuilding/decimating the geometry is unnecessary.
	var surfaces: Array = mesh.get("_surfaces").duplicate(true)
	for surface: Dictionary in surfaces:
		surface["lods"] = []
	var full_mesh := ArrayMesh.new()
	full_mesh.set("_surfaces", surfaces)
	full_mesh.custom_aabb = (mesh as ArrayMesh).custom_aabb
	# Keep the importer's position-only shadow mesh and its shadow LODs.
	# Visible canopy buffers above remain at their approved full detail.
	full_mesh.shadow_mesh = (mesh as ArrayMesh).shadow_mesh
	full_mesh.set_meta("full_detail_canopy", true)
	_canopy_meshes[identity] = full_mesh
	return full_mesh


func _first_mesh_instance(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node as MeshInstance3D
	for child: Node in node.get_children():
		var found := _first_mesh_instance(child)
		if found != null:
			return found
	return null


func _fail_restore(message: String) -> void:
	restore_error = message
	push_error(message)
