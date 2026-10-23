extends SceneTree

const SAMPLE := preload("res://runtime/lab/m01_optical_sample.gd")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	create_timer(30.0).timeout.connect(func() -> void: quit(2))
	var host := (load("res://main.tscn") as PackedScene).instantiate()
	SAMPLE.isolate_host(host)
	for light: Node in host.find_children("*", "Light3D", true, false):
		if not _require(not light.visible, "A host light leaks into the M01 experiment"):
			return
	host.free()
	var sample := SAMPLE.new()
	root.add_child(sample)
	if not _require(sample.counts["meshes"] == 917, "M01 source mesh count changed"):
		return
	if not _require(sample.counts["sheen"] == 7 and sample.counts["clearcoat"] == 10 and sample.counts["glass"] >= 1, "Source optical metadata was not imported"):
		return
	var environments := sample.find_children("*", "WorldEnvironment", true, false)
	if not _require(environments.size() == 1 and environments[0].environment.reflected_light_source == Environment.REFLECTION_SOURCE_SKY, "M01 has no environment reflections"):
		return
	var shadow_lights := 0
	for light: Node in sample.find_children("*", "Light3D", true, false):
		if light.shadow_enabled:
			shadow_lights += 1
			if not _require(light is DirectionalLight3D, "An extra shadowed point light changes reference lighting"):
				return
	if not _require(shadow_lights == 1, "The reference sun shadow is missing"):
		return
	if not _require(sample.counts["triangles"] == 1993542, "M01 geometry was reduced"):
		return
	for node: Node in sample.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if not _require(mesh.global_basis.determinant() > 0.0, "A mirrored double-sided draw can invert M01 lighting"):
			return
		if mesh.has_meta("m01_source_mesh"):
			var source_mesh := mesh.get_meta("m01_source_mesh") as ArrayMesh
			var source_frame: Transform3D = mesh.get_meta("m01_source_frame")
			for surface in range(source_mesh.get_surface_count()):
				var before := source_mesh.surface_get_arrays(surface)
				var after := mesh.mesh.surface_get_arrays(surface)
				var vertices_before := before[Mesh.ARRAY_VERTEX] as PackedVector3Array
				var vertices_after := after[Mesh.ARRAY_VERTEX] as PackedVector3Array
				if not _require(vertices_before.size() == vertices_after.size() and source_mesh.surface_get_array_index_len(surface) == mesh.mesh.surface_get_array_index_len(surface), "Mirror normalization reduced geometry"):
					return
				for index in [0, vertices_before.size() / 2, vertices_before.size() - 1]:
					if not _require((source_frame * vertices_before[index]).distance_to(mesh.global_transform * vertices_after[index]) < 0.00001, "Mirror normalization moved world geometry"):
						return
		for surface_data: Dictionary in mesh.mesh.get("_surfaces"):
			if not _require(surface_data.get("lods", []).is_empty(), "An automatic LOD can reduce M01 geometry"):
				return
		if not _require(str((mesh.get_meta("extras", {}) as Dictionary).get("module", "")) == "M01", "Non-M01 geometry entered the experiment"):
			return
		for surface in range(mesh.mesh.get_surface_count()):
			var original := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
			var actual := mesh.get_active_material(surface)
			var color: Color = actual.get_shader_parameter("source_albedo") if actual is ShaderMaterial else (actual as BaseMaterial3D).albedo_color
			if not _require(color.r == original.albedo_color.r and color.g == original.albedo_color.g and color.b == original.albedo_color.b, "A source RGB value changed"):
				return
			var definition: Dictionary = original.get_meta("m01_reference_optics", {})
			var coat: Dictionary = definition.get("extensions", {}).get("KHR_materials_clearcoat", {})
			if not coat.is_empty() and not actual is ShaderMaterial and float(coat.get("clearcoatRoughnessFactor", 0.0)) == 0.0:
				if not _require(is_equal_approx(0.001 + 0.099 * actual.clearcoat_roughness, 0.0525 * 0.0525), "Clearcoat minimum lobe differs from the reference"):
					return
			var factor: Array = definition.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
			var linear := color.srgb_to_linear()
			if not _require(absf(linear.r - float(factor[0])) < 0.00001 and absf(linear.g - float(factor[1])) < 0.00001 and absf(linear.b - float(factor[2])) < 0.00001, "Imported color differs from authored linear RGB: " + original.resource_name + " " + str(color)):
				return
	if not _require(sample.find_children("*", "MultiMeshInstance3D", true, false).is_empty(), "Landscape instances were loaded"):
		return
	print("M01_OPTICAL_SAMPLE_NATIVE_PASS ", JSON.stringify(sample.counts))
	sample.free()
	quit(0)


func _require(condition: bool, message: String) -> bool:
	if not condition:
		push_error(message)
		quit(1)
	return condition
