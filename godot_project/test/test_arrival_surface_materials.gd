extends SceneTree
const LIGHTING := preload("res://nest/buildings/main/arrival/estate_arrival_lighting.gd")
func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok
func run() -> void:
	var nest := load("res://nest/nest.tscn").instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	var platform := nest.find_child("Roof01 complete raised landing platform",true,false) as MeshInstance3D
	var original_faces := platform.mesh.get_faces()
	var original_uv: Array = []
	for surface in range(platform.mesh.get_surface_count()):
		original_uv.append(platform.mesh.surface_get_arrays(surface)[Mesh.ARRAY_TEX_UV])
		var material := platform.get_active_material(surface) as BaseMaterial3D
		if material == null:
			print("PLATFORM_NATIVE_SHADER ",surface," ",platform.get_active_material(surface))
			continue
		print("PLATFORM_SOURCE ",surface," ",material.resource_name," alpha=",material.albedo_color.a," transparency=",material.transparency," uv=",material.uv1_scale," offset=",material.uv1_offset," depth=",material.no_depth_test," override=",platform.material_override)
	var light := LIGHTING.new()
	nest.add_child(light)
	light.bind(nest)
	print("ARRIVAL_BINDINGS ",light.bindings.size())
	var feathered := 0
	for item: Dictionary in light.bindings:
		if (item.source as BaseMaterial3D).transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			feathered += 1
			if not require((item.material as ShaderMaterial).shader == LIGHTING.FIXTURE and (item.material as ShaderMaterial).shader.code.contains("depth_draw_never"), "Feathered light cards lost alpha/translucent rendering"): return
		if item.group not in ["platform_disc","platform_ring","platform_side"]: continue
		print("PLATFORM_EVENT ",item.group," ",item.source.resource_name)
		if not require((item.material as ShaderMaterial).get_shader_parameter("source_texture") == (item.source as BaseMaterial3D).albedo_texture and (item.material as ShaderMaterial).get_shader_parameter("emission_texture") == (item.source as BaseMaterial3D).emission_texture, "Arrival changed original platform pattern textures"): return
		var shader := (item.material as ShaderMaterial).shader.code
		if not require(not shader.contains("depth_draw_never") and not shader.contains("ALPHA="),"Opaque arrival apparatus must write depth; transparent sorting exposes closed-mesh triangles"): return
	if not require(feathered >= 3, "Actual petal-root feathered light cards were not exercised"): return
	light.sample(8.2)
	light.sample(0.0)
	light.sample(8.2)
	light.sample(100.0)
	if not require(platform.mesh.get_faces() == original_faces, "Arrival deformed platform triangles"): return
	for surface in range(platform.mesh.get_surface_count()):
		if not require(platform.mesh.surface_get_arrays(surface)[Mesh.ARRAY_TEX_UV] == original_uv[surface], "Arrival changed original pattern UV coordinates"): return
	nest.free()
	print("PASS arrival surface depth and replay")
	quit()
