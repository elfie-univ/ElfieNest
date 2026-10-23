extends RefCounted
## Shared rendering correction for untextured opaque physical surfaces.

const OPAQUE := preload("res://rooms/estate/estate_opaque.gdshader")
const SHEEN := preload("res://runtime/lab/m01_sheen.gdshader")
const GLASS := preload("res://rooms/estate/estate_glass.gdshader")


static func supports(material: BaseMaterial3D, allow_vertex_color: bool = false) -> bool:
	# Preserve specialized, textured and emissive materials on their existing path.
	return (
		material is StandardMaterial3D
		and material.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED
		and material.shading_mode == BaseMaterial3D.SHADING_MODE_PER_PIXEL
		and not material.emission_enabled
		and (allow_vertex_color or not material.vertex_color_use_as_albedo)
		and material.albedo_texture == null
		and material.normal_texture == null
		and material.roughness_texture == null
		and material.metallic_texture == null
		and material.ao_texture == null
	)


static func make_material(original: BaseMaterial3D, coat: float = 0.0, coat_roughness: float = 0.0, vertex_color: bool = false) -> ShaderMaterial:
	var result := ShaderMaterial.new()
	result.resource_name = original.resource_name
	for key in original.get_meta_list():
		result.set_meta(key, original.get_meta(key))
	result.set_meta("source_material", original)
	result.shader = OPAQUE
	result.set_shader_parameter("source_albedo", original.albedo_color)
	result.set_shader_parameter("source_roughness", original.roughness)
	result.set_shader_parameter("source_metallic", original.metallic)
	result.set_shader_parameter("source_specular", original.metallic_specular)
	result.set_shader_parameter("source_clearcoat", coat)
	result.set_shader_parameter("source_coat_roughness", coat_roughness)
	result.set_shader_parameter("use_linear_vertex_color", vertex_color)
	result.set_shader_parameter("use_authored_reflection", (original.get_meta("extras", {}) as Dictionary).has("preview_surface_finish"))
	return result


static func specular_from_ior(ior: float) -> float:
	# Compatibility F0 = .16 * SPECULAR^2 (the default .5 gives F0=.04).
	return absf((ior - 1.0) / (ior + 1.0)) / 0.4


static func make_glass(original: BaseMaterial3D, optics: Dictionary) -> ShaderMaterial:
	var result := ShaderMaterial.new()
	result.resource_name = original.resource_name
	result.shader = GLASS
	result.set_meta("source_material", original)
	result.set_shader_parameter("source_albedo", original.albedo_color)
	result.set_shader_parameter("source_roughness", original.roughness)
	for key: String in ["transmission", "ior", "clearcoat", "clearcoat_roughness"]:
		var parameter := "coat_roughness" if key == "clearcoat_roughness" else key
		result.set_shader_parameter("source_" + parameter, float(optics.get(key, 1.5 if key == "ior" else 0.0)))
	var film: Dictionary = optics.get("iridescence", {})
	result.set_shader_parameter("source_iridescence", float(film.get("iridescenceFactor", 0.0)))
	result.set_shader_parameter("source_film_ior", float(film.get("iridescenceIor", 1.3)))
	result.set_shader_parameter("source_film_thickness", float(film.get("iridescenceThicknessMaximum", 400.0)))
	result.set_shader_parameter("source_emission", original.emission if original.emission_enabled else Color.BLACK)
	# Complete glTF definitions are already carried by the source importer;
	# read the optional volume directly, without another runtime asset read.
	var definition := original.get_meta("m01_reference_optics", {}) as Dictionary
	var volume := (definition.get("extensions", {}) as Dictionary).get("KHR_materials_volume", {}) as Dictionary
	result.set_shader_parameter("source_thickness", float(volume.get("thicknessFactor", 0.0)))
	result.set_shader_parameter("source_attenuation_distance", float(volume.get("attenuationDistance", 0.0)))
	var tint: Array = volume.get("attenuationColor", [1, 1, 1])
	result.set_shader_parameter("source_attenuation_color", Color(float(tint[0]), float(tint[1]), float(tint[2])))
	return result


static func make_sheen(original: BaseMaterial3D, definition: Dictionary) -> ShaderMaterial:
	var result := ShaderMaterial.new()
	result.resource_name = original.resource_name
	result.shader = SHEEN
	result.set_meta("source_material", original)
	result.set_shader_parameter("source_albedo", original.albedo_color)
	result.set_shader_parameter("source_roughness", original.roughness)
	result.set_shader_parameter("source_normal", original.normal_texture)
	result.set_shader_parameter("source_normal_scale", original.normal_scale)
	var color: Array = definition.get("sheenColorFactor", [0, 0, 0])
	result.set_shader_parameter("sheen_color", Vector3(float(color[0]), float(color[1]), float(color[2])))
	result.set_shader_parameter("sheen_roughness", float(definition.get("sheenRoughnessFactor", 0.8)))
	result.set_shader_parameter("use_authored_reflection", (original.get_meta("extras", {}) as Dictionary).has("preview_surface_finish"))
	return result


static func repair_window_normals(instance: MeshInstance3D, cache: Dictionary) -> void:
	var extras := instance.get_meta("extras", {}) as Dictionary
	if str(extras.get("source_name", "")) != "ROOM • front fitted deep reveal" or not instance.mesh is ArrayMesh:
		return
	var source := instance.mesh as ArrayMesh
	var identity := source.get_instance_id()
	if not cache.has(identity):
		var result := ArrayMesh.new()
		for surface in range(source.get_surface_count()):
			var arrays := source.surface_get_arrays(surface)
			var positions := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			var indices := arrays[Mesh.ARRAY_INDEX] as PackedInt32Array
			var normals := PackedVector3Array()
			normals.resize(positions.size())
			# The saved boolean reveal carries smoothed normals from distant
			# faces across large planar triangles. Area-weighted local topology
			# restores the surface normal without moving or deleting any face.
			for index in range(0, indices.size(), 3):
				var a := indices[index]
				var b := indices[index + 1]
				var c := indices[index + 2]
				var face := (positions[c] - positions[a]).cross(positions[b] - positions[a])
				for vertex in [a, b, c]:
					normals[vertex] += face
			var original_normals := arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array
			for vertex in range(normals.size()):
				normals[vertex] = normals[vertex].normalized() if normals[vertex].length_squared() > 0.000000000001 else original_normals[vertex]
			arrays[Mesh.ARRAY_NORMAL] = normals
			result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays)
			result.surface_set_material(surface, source.surface_get_material(surface))
		result.custom_aabb = source.custom_aabb
		cache[identity] = result
	instance.mesh = cache[identity]
