extends SceneTree

const SURFACE := preload("res://rooms/estate/estate_surface.gd")
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const SAMPLE := preload("res://runtime/lab/m01_optical_sample.gd")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	create_timer(50.0).timeout.connect(func() -> void: quit(2))
	var source := (load(SAMPLE.SOURCE) as PackedScene).instantiate() as Node3D
	root.add_child(source)
	var frames := {}
	var meshes := {}
	var originals := {}
	for node: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		frames[node.get_instance_id()] = node.global_transform
		meshes[node.get_instance_id()] = node.mesh
		originals[node.get_instance_id()] = []
		for surface in range(node.mesh.get_surface_count()):
			originals[node.get_instance_id()].append(node.get_active_material(surface))
	var counts := DAYLIGHT.apply(source)
	var checked := 0
	var mirrored := 0
	var modules := {}
	for node: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		assert(node.global_transform == frames[node.get_instance_id()], "Rendering changed an authority frame")
		if node.mesh != meshes[node.get_instance_id()]:
			var before := meshes[node.get_instance_id()] as ArrayMesh
			for surface in range(before.get_surface_count()):
				var old_arrays := before.surface_get_arrays(surface)
				var new_arrays := node.mesh.surface_get_arrays(surface)
				for attribute in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_INDEX, Mesh.ARRAY_TEX_UV]:
					assert(old_arrays[attribute] == new_arrays[attribute], "Window normal repair changed positions, topology or UV")
		for surface in range(node.mesh.get_surface_count()):
			var actual := node.get_active_material(surface)
			if bool(node.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR):
				assert(not actual is ShaderMaterial, "Vertex-painted vegetation lost its color material")
			if not actual is ShaderMaterial or actual.shader != SURFACE.OPAQUE:
				continue
			var original := originals[node.get_instance_id()][surface] as BaseMaterial3D
			assert(SURFACE.supports(original), "A specialized material entered the plain-surface shader")
			assert(actual.get_shader_parameter("source_albedo") == original.albedo_color, "Original RGB changed")
			assert(actual.get_shader_parameter("source_roughness") == original.roughness, "Authored roughness changed")
			assert(actual.get_shader_parameter("source_metallic") == original.metallic)
			var optics: Dictionary = original.get_meta("source_optics", {})
			assert(is_equal_approx(actual.get_shader_parameter("source_clearcoat"), float(optics.get("clearcoat", 0.0))), "Source clearcoat missing")
			checked += 1
			mirrored += int(node.global_basis.determinant() < 0.0)
			modules[str((node.get_meta("extras", {}) as Dictionary).get("module", "landscape"))] = true
	for ior in [1.12, 1.46, 1.5]:
		assert(is_equal_approx(0.16 * pow(SURFACE.specular_from_ior(ior), 2), pow((ior - 1.0) / (ior + 1.0), 2)), "IOR Fresnel mapping is wrong")
	assert(checked > 1000 and mirrored > 0 and modules.has("central") and modules.has("M01") and modules.has("M08"), "Full-scene surface coverage missing")
	print("ESTATE_SURFACE_NATIVE_PASS ", JSON.stringify({"surfaces": checked, "mirrored": mirrored, "modules": modules.keys(), "daylight": counts}))
	source.free()
	var sample := SAMPLE.new()
	root.add_child(sample)
	assert(sample.counts["triangles"] == 1993542 and sample.counts["meshes"] == 917)
	var window_surfaces := 0
	for mesh: MeshInstance3D in sample.find_children("*", "MeshInstance3D", true, false):
		for surface in range(mesh.mesh.get_surface_count()):
			var actual := mesh.get_active_material(surface)
			if actual.resource_name == "02 • porcelain window reveals":
				assert(actual is ShaderMaterial and actual.shader == SURFACE.OPAQUE, "Window specular AA missing")
				assert(is_equal_approx(actual.get_shader_parameter("source_roughness"), 0.25), "Window source roughness changed")
				window_surfaces += 1
	assert(window_surfaces > 0)
	print("M01_WINDOW_SURFACE_PASS surfaces=", window_surfaces)
	sample.free()
	quit(0)
