extends SceneTree

# Architectural slabs can be both the upper floor and the lower ceiling.
# Room lamp masks must never make the same surface receive two copies of sunlight.
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var control := preload("res://nest/rendering/estate_lighting_sample.gd").new()
	control.bind_m01(estate)
	control.apply_environment(1.0, false, true)
	var suns: Array[DirectionalLight3D] = []
	for light: DirectionalLight3D in estate.find_children("*", "DirectionalLight3D", true, false):
		if light.is_visible_in_tree() and light.light_energy > 0.0 and light.shadow_enabled: suns.append(light)
	var expected_fills := {"CourtyardReferenceFillCool":0.65/PI,"CourtyardReferenceFillFront":0.30/PI,"NativeHemisphereUpper":0.72/PI,"NativeHemisphereLower":0.72/PI}
	for label: String in expected_fills:
		var fill := estate.find_child(label,true,false) as DirectionalLight3D
		if fill == null or not fill.visible or not is_equal_approx(fill.light_energy,expected_fills[label]):
			failures.append("Original daytime light missing or changed: " + label)
	for sun: DirectionalLight3D in suns:
		if not is_equal_approx(sun.light_energy,1.05/PI*0.04): failures.append("Global sun still uses the lakeside-era 25x increase")
	var duplicate_receivers: Array[Dictionary] = []
	var uncovered := 0
	var checked := 0
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or not mesh.is_visible_in_tree() or mesh.layers == 0: continue
		var count := 0
		for sun: DirectionalLight3D in suns:
			if mesh.layers & sun.light_cull_mask: count += 1
		checked += 1
		if count == 0: uncovered += 1
		if count > 1:
			duplicate_receivers.append({"path":str(estate.get_path_to(mesh)),"layers":mesh.layers,"sun_count":count,"extras":mesh.get_meta("extras",{})})
	if not duplicate_receivers.is_empty(): failures.append("A surface receives the same physical sun more than once")
	if uncovered > 0: failures.append("Visible scene geometry is excluded from sunlight")
	var day_state := _state(estate)
	var phases := [[0.0,true,false],[0.0,true,true],[1.0,false,false]]
	for phase: Array in phases:
		control.apply_environment(phase[0],phase[1],true,phase[2])
		for batch: MultiMeshInstance3D in estate.find_children("*","MultiMeshInstance3D",true,false):
			for surface in range(batch.multimesh.mesh.get_surface_count()):
				var material := batch.material_override if batch.material_override != null else batch.multimesh.mesh.surface_get_material(surface)
				if material is ShaderMaterial and material.shader == preload("res://nest/rendering/estate_opaque.gdshader"):
					var scale: Variant = material.get_shader_parameter("natural_light_scale")
					if scale == null or not is_equal_approx(float(scale),float(phase[0])):
						if not failures.has("Instanced foliage retains daytime irradiance at night"): failures.append("Instanced foliage retains daytime irradiance at night")
		if phase[0] == 0.0:
			for sun: DirectionalLight3D in estate.find_children("*","DirectionalLight3D",true,false):
				if sun.visible or sun.light_energy != 0.0: failures.append("Night receives sunlight")
	if _state(estate) != day_state: failures.append("Day/night/day switching changes daytime light state")
	var result := {"checked_meshes":checked,"active_suns":suns.size(),"uncovered":uncovered,"duplicate_receivers":duplicate_receivers,"failures":failures}
	var output := FileAccess.open("res://../build/asset_design/daylight-audit/solar-receivers.json",FileAccess.WRITE)
	if output != null: output.store_string(JSON.stringify(result,"  "));output.close()
	for failure: String in failures: push_error(failure)
	print("SOLAR_RECEIVERS checked=",checked," duplicated=",duplicate_receivers.size()," uncovered=",uncovered," failures=",failures.size())
	estate.free()
	quit(0 if failures.is_empty() else 1)

func _state(estate: Node3D) -> Array:
	var result: Array = []
	for light: Light3D in estate.find_children("*","Light3D",true,false):
		result.append([str(estate.get_path_to(light)),light.visible,light.light_energy,light.light_color,light.light_cull_mask,light.shadow_enabled,light.shadow_caster_mask])
	return result
