extends SceneTree

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	create_timer(40.0).timeout.connect(func() -> void: quit(2))
	var imported := (load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene).get_state()
	for node_index in range(imported.get_node_count()):
		if imported.get_node_type(node_index) == &"DirectionalLight3D":
			var properties := {}
			for property_index in range(imported.get_node_property_count(node_index)):
				properties[str(imported.get_node_property_name(node_index, property_index))] = str(imported.get_node_property_value(node_index, property_index))
			print("DAYLIGHT_SOURCE_SUN ", JSON.stringify(properties))
	var fixture := Node3D.new()
	root.add_child(fixture)
	var sun := DirectionalLight3D.new()
	sun.light_energy = 2.7
	sun.light_color = Color(1, 0.85, 0.58)
	fixture.add_child(sun)
	var lamp := StandardMaterial3D.new()
	lamp.resource_name = "Soft warm continuous U doorway light"
	lamp.emission_enabled = true
	lamp.emission = Color(4, 2.3, 0.9)
	lamp.albedo_color = Color(0.98, 0.87, 0.68)
	lamp.roughness = 0.85
	var first := _mesh(fixture, lamp)
	first.set_meta("extras", {"module": "central"})
	var second := _mesh(fixture, lamp)
	var sky := StandardMaterial3D.new()
	sky.resource_name = "Approved blue sky white clouds dome inner side"
	sky.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var sky_mesh := _mesh(fixture, sky)
	var screen := StandardMaterial3D.new()
	screen.resource_name = "TV illuminated landscape display"
	screen.emission_enabled = true
	var screen_mesh := _mesh(fixture, screen)
	var bounce_materials: Array[StandardMaterial3D] = []
	var bounce_meshes: Array[MeshInstance3D] = []
	for material_name: String in ["Niche V1 softly illuminated warm plaster returns", "L1 continuous warm ivory plaster", "L1 double cove baked warm ceiling bounce", "L2 complete distributed ceiling bounce", "L1 inner sofa background honey oak with baked warm wash", "V048 subtle ice-aqua window reveal luminous return"]:
		var bounce := StandardMaterial3D.new()
		bounce.resource_name = material_name
		bounce.emission_enabled = true
		bounce.emission = Color(0.16, 0.074, 0.018)
		bounce_materials.append(bounce)
		bounce_meshes.append(_mesh(fixture, bounce))
	var glass := StandardMaterial3D.new()
	glass.resource_name = "06 • clear observation glass.001"
	glass.albedo_color = Color(0.97, 0.99, 1, 1)
	glass.roughness = 0.05
	glass.refraction_enabled = true
	var glass_mesh := _mesh(fixture, glass)
	glass_mesh.set_meta("extras", {"module": "M01", "glass": true})
	var facade := StandardMaterial3D.new()
	facade.resource_name = "Trial nearly clear ice-aqua facade glass"
	facade.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	facade.albedo_color = Color(0.91, 0.98, 1, 0.18)
	facade.roughness = 0.008
	var facade_mesh := _mesh(fixture, facade)
	var shell := StandardMaterial3D.new()
	shell.resource_name = "EXTERIOR • M01 鼠尾草绿 #95B58C"
	shell.albedo_color = Color(0.58, 0.71, 0.55)
	var shell_mesh := _mesh(fixture, shell)
	shell_mesh.set_meta("extras", {"module": "M01"})
	var pod_furniture := _mesh(fixture, shell)
	pod_furniture.set_meta("extras", {"module": "M01", "floor": 1, "furniture": true})
	DAYLIGHT.apply(fixture)
	for index in range(bounce_materials.size()):
		if not _require(bounce_meshes[index].get_active_material(0) == bounce_materials[index] and bounce_materials[index].emission_enabled, "Authored bounce was switched off with powered lamps"):
			return
	var clear_facade := facade_mesh.get_active_material(0) as BaseMaterial3D
	if not _require(clear_facade != facade and clear_facade.albedo_color == facade.albedo_color and clear_facade.roughness == facade.roughness and clear_facade.depth_draw_mode == BaseMaterial3D.DEPTH_DRAW_DISABLED, "Facade glazing color, alpha or roughness changed, or still writes depth"):
		return
	if not _require(first.layers == (3 | (1 << 5)) and second.layers == 5, "Interior fill leaked to untagged outdoor geometry"):
		return
	var clear_glass := glass_mesh.get_active_material(0) as BaseMaterial3D
	if not _require(is_equal_approx(0.16 * pow(clear_glass.metallic_specular, 2), pow((1.12 - 1.0) / (1.12 + 1.0), 2)) and is_equal_approx(0.16 * pow(clear_facade.metallic_specular, 2), pow((1.46 - 1.0) / (1.46 + 1.0), 2)), "Glass reflection uses plastic's default F0 instead of source IOR"):
		return
	if not _require(clear_glass != glass and clear_glass.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA and not clear_glass.refraction_enabled and is_equal_approx(clear_glass.albedo_color.a, DAYLIGHT.OBSERVATION_GLASS_ALPHA), "Observation glass still renders as an opaque pane"):
		return
	if not _require(clear_glass.albedo_color.r == glass.albedo_color.r and clear_glass.albedo_color.g == glass.albedo_color.g and clear_glass.albedo_color.b == glass.albedo_color.b and clear_glass.roughness == glass.roughness and glass.albedo_color.a == 1.0, "Glazing RGB/roughness or imported resource changed"):
		return
	if not _require(glass_mesh.layers == (5 | (1 << 8)) and shell_mesh.layers == (5 | (1 << 8)) and shell_mesh.get_active_material(0) is ShaderMaterial and shell_mesh.get_active_material(0).get_shader_parameter("source_albedo") == shell.albedo_color, "Facade uses interior fill or was recolored"):
		return
	if not _require(pod_furniture.layers == (13 | (1 << 8)), "Furniture contact layer or outdoor fill isolation is missing"):
		return
	var calibrated := first.get_active_material(0) as BaseMaterial3D
	if not _require(calibrated != lamp and lamp.emission_enabled, "Daylight mutated the original material"):
		return
	if not _require(calibrated.emission_enabled, "Source fixture emission was switched off by its name"):
		return
	if not _require(second.get_active_material(0) == calibrated, "Shared material was duplicated per fixture"):
		return
	if not _require(calibrated.albedo_color == lamp.albedo_color and calibrated.roughness == lamp.roughness, "Surface appearance was modified"):
		return
	if not _require(sky_mesh.get_active_material(0) == sky and sky_mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF, "Approved sky was modified or blocks daylight"):
		return
	if not _require(screen_mesh.get_active_material(0) == screen and screen.emission_enabled, "Screen content was disabled with lamps"):
		return
	if not _require(sun.shadow_enabled and is_equal_approx(sun.light_energy, DAYLIGHT.SUN_ENERGY) and sun.light_color == DAYLIGHT.SUN_COLOR, "Daylight is not neutral and shadowed"):
		return
	fixture.queue_free()
	await process_frame
	var nest := (load("res://rooms/nest.tscn") as PackedScene).instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	await process_frame
	var environment := (nest.get_node("WorldEnvironment") as WorldEnvironment).environment
	if not _require(environment.sky != null and environment.sky.sky_material is ShaderMaterial and environment.ambient_light_source == Environment.AMBIENT_SOURCE_COLOR and environment.reflected_light_source == Environment.REFLECTION_SOURCE_SKY, "Neutral ambient and authored reflections are not separated"):
		return
	# Match the reference hemisphere's mean irradiance in linear light, not an
	# arbitrary gray/exposure lift. Use the same energy and exposure units as the reference sample.
	var reference_ambient := ((Color.hex(0xd7ebffff).srgb_to_linear() + Color.hex(0x5a685dff).srgb_to_linear()) * 0.5).linear_to_srgb()
	if not _require(absf(environment.ambient_light_color.r - reference_ambient.r) < 0.002 and absf(environment.ambient_light_color.g - reference_ambient.g) < 0.002 and absf(environment.ambient_light_color.b - reference_ambient.b) < 0.002, "Ambient does not match reference hemisphere mean irradiance"):
		return
	if not _require(environment.background_mode == Environment.BG_COLOR and environment.tonemap_mode == Environment.TONE_MAPPER_ACES and is_equal_approx(environment.tonemap_exposure, 0.88), "Cloud backdrop, reference ACES response or unchanged exposure is missing"):
		return
	var environment_material := environment.sky.sky_material as ShaderMaterial
	if not _require(environment_material.shader == load("res://rooms/estate/estate_reflection_sky.gdshader"), "Environment does not use the reference-derived reflection field"):
		return
	var estate := nest.get_node("Generated/CompleteEstate")
	var source := estate.get_node("CompleteFinal")
	var review_camera := nest.get_node("Generated/courtyard") as Camera3D
	var third_floor_camera := nest.get_node("Generated/central-3") as Camera3D
	if not _require(third_floor_camera.global_position.is_equal_approx(nest.to_global(Vector3(0, 8.5, 3.2))), "Third-floor review camera is inside the ceiling or cabinet"):
		return
	if not _require(review_camera.position.is_equal_approx(ModularNest.REFERENCE_REVIEW_POSITION) and (-review_camera.basis.z).dot((ModularNest.REFERENCE_REVIEW_TARGET - review_camera.position).normalized()) > 0.999 and is_equal_approx(review_camera.fov, 42.0), "Review camera does not match the reference position/target/FOV"):
		return
	if not _require(nest.get_node("CeilingFill").light_cull_mask == DAYLIGHT.INTERIOR_FILL_LAYER, "Ceiling fill is not restricted to building geometry"):
		return
	var sun_count := 0
	var preserved_fixture_emission_count := 0
	var preserved_sky_count := 0
	var glazing_modules := {}
	var preserved_interior_floors := 0
	var naturally_lit_pod_floors := 0
	var restored_finishes := {}
	for light: Node in source.find_children("*", "DirectionalLight3D", true, false):
		if str(light.name).begins_with("NativeHemisphere"):
			if not _require((light as DirectionalLight3D).light_cull_mask == DAYLIGHT.NATIVE_HEMISPHERE_LAYER and (light as DirectionalLight3D).light_specular == 0.0, "Textured hemisphere changes physical-surface irradiance or reflection"):
				return
			continue
		sun_count += 1
		var expected_energy := DAYLIGHT.OUTDOOR_SUN_ENERGY if light.name == &"CourtyardDaylight" else DAYLIGHT.SUN_ENERGY
		var expected_mask := (DAYLIGHT.OUTDOOR_LIGHT_LAYER | DAYLIGHT.LANDSCAPE_LIGHT_LAYER) if light.name == &"CourtyardDaylight" else DAYLIGHT.INTERIOR_FILL_LAYER
		if light.has_meta("reference_intensity"):
			expected_energy = float(light.get_meta("reference_intensity")) / PI
			expected_mask = DAYLIGHT.INTERIOR_FILL_LAYER | DAYLIGHT.OUTDOOR_LIGHT_LAYER | DAYLIGHT.LANDSCAPE_LIGHT_LAYER
		if not _require(is_equal_approx((light as DirectionalLight3D).light_energy, expected_energy) and (light as DirectionalLight3D).light_cull_mask == expected_mask, "Full estate bypassed daylight calibration"):
			return
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		var uses_fill := DAYLIGHT._uses_interior_fill(mesh)
		if not _require(bool(mesh.layers & DAYLIGHT.INTERIOR_FILL_LAYER) == uses_fill, "Building/outdoor fill assignment changed"):
			return
		if not _require(bool(mesh.layers & DAYLIGHT.OUTDOOR_LIGHT_LAYER) != uses_fill, "Outdoor sunlight leaked into the accepted interior"):
			return
		if mesh.name == &"Central L1 fitted complete floor":
			if not _require(uses_fill, "Accepted interior floor lost its fill"):
				return
			preserved_interior_floors += 1
		elif "continuous lower floor" in str(extras.get("source_name", "")):
			if not _require(not uses_fill, "Pod floor still uses the bright interior rig"):
				return
			naturally_lit_pod_floors += 1
		for surface in range(mesh.mesh.get_surface_count()):
			var actual := mesh.get_active_material(surface)
			var imported_material := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
			if str(extras.get("source_name", "")) == "ROOM • sculpted continuous shell" and load("res://rooms/estate/estate_surface.gd").supports(imported_material, true):
				if not _require(actual is ShaderMaterial, "Vertex-color flag bypassed the shared shell lighting correction"):
					return
			if bool(extras.get("roof_skylight", false)):
				print("ROOF_GLASS_BINDING ", mesh.name, " material=", actual.get_class(), " shader=", actual.shader.resource_path if actual is ShaderMaterial else "", " version=", extras.get("exportVersion", ""), " optics=", (mesh.mesh.surface_get_material(surface) as BaseMaterial3D).get_meta("source_optics", {}))
				if not _require(actual is ShaderMaterial and actual.shader == load("res://rooms/estate/estate_glass.gdshader") and str(extras.get("exportVersion", "")) == "building_central_v051", "Actual v051 roof did not bind the thin-glass shader"):
					return
			if actual is ShaderMaterial:
				if not _require((mesh.layers & DAYLIGHT.NATIVE_HEMISPHERE_LAYER) == 0, "Mixed-surface mesh receives hemisphere irradiance twice"):
					return
				var original := actual.get_meta("source_material") as BaseMaterial3D
				if actual.shader == load("res://rooms/estate/estate_opaque.gdshader") or actual.shader == load("res://runtime/lab/m01_sheen.gdshader"):
					if not _require(bool(actual.get_shader_parameter("use_authored_reflection")) == (original.get_meta("extras", {}) as Dictionary).has("preview_surface_finish"), "Studio reflection leaked onto a surface without an authored environment"):
						return
				if actual.shader == load("res://rooms/estate/estate_opaque.gdshader"):
					var vertex_color := bool(mesh.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) and original.vertex_color_use_as_albedo
					if not _require(bool(actual.get_shader_parameter("use_linear_vertex_color")) == vertex_color, "Shared material confused colored and uncolored primitive inputs"):
						return
				if not _require(actual.get_shader_parameter("source_albedo") == original.albedo_color and actual.get_shader_parameter("source_roughness") == original.roughness, "Plain surface source RGB/roughness changed"):
					return
				if (original.get_meta("extras", {}) as Dictionary).has("preview_surface_finish"):
					if not _require(float(actual.get_shader_parameter("source_clearcoat")) > 0.0, "Authored clearcoat missing"):
						return
					restored_finishes[original.resource_name] = true
				continue
			var material := actual as BaseMaterial3D
			if material == null:
				continue
			if (material.get_meta("extras", {}) as Dictionary).has("preview_surface_finish"):
				var original_finish := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
				if not _require(material.clearcoat_enabled and material.clearcoat > 0.0 and material.roughness == original_finish.roughness and material.albedo_color.r == original_finish.albedo_color.r and material.albedo_color.g == original_finish.albedo_color.g and material.albedo_color.b == original_finish.albedo_color.b, "Authored clearcoat missing or source finish RGB/roughness changed"):
					return
				if not restored_finishes.has(material.resource_name):
					print("AUTHORED_OPTICS ", material.resource_name, " imported_coat=", original_finish.clearcoat_enabled, " coat=", material.clearcoat, " coat_roughness=", material.clearcoat_roughness)
				restored_finishes[material.resource_name] = true
			if DAYLIGHT._is_observation_glass(material.resource_name.to_lower()):
				glazing_modules[str(extras.get("module", ""))] = true
				var original := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
				if not _require(material.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA and material.albedo_color.a < 0.2 and not uses_fill, "Full estate glazing stayed opaque or overlit"):
					return
				if str(extras.get("module", "")) == "M01":
					print("GLASS_IMPORT original_transparency=", original.transparency, " original_alpha=", original.albedo_color.a, " rendered_alpha=", material.albedo_color.a)
			if DAYLIGHT._is_background(material.resource_name.to_lower()):
				preserved_sky_count += 1
			elif DAYLIGHT._is_artificial(material.resource_name.to_lower()) and material.emission_enabled:
				preserved_fixture_emission_count += 1
	# The source sun plus one key and two reference fills share CompleteFinal.
	var reference_fills := estate.find_children("CourtyardReferenceFill*", "DirectionalLight3D", true, false)
	if not _require(restored_finishes.size() == 5, "Five authored finish families were not restored"):
		return
	if not _require(sun_count == 4 and reference_fills.size() == 2 and preserved_fixture_emission_count > 100 and preserved_sky_count > 0, "Full estate reference light or approved sky coverage is missing"):
		return
	var fixtures := source.find_children("*", "Light3D", true, false).filter(func(light: Node) -> bool: return light.get_meta("asset_role", "") == "authored-daylight-fixture")
	var room_fills := source.find_children("ReferenceRoomFill*", "OmniLight3D", true, false)
	if not _require(room_fills.size() == 8, "Reference's shared daytime room fills are missing"):
		return
	for room_fill: OmniLight3D in room_fills:
		if not _require(is_equal_approx(room_fill.light_energy, 3.0 / PI) and is_equal_approx(room_fill.omni_range, 8.0), "Reference room fill units changed"):
			return
	if not _require(fixtures.size() == 215, "Authored fixture definitions were not restored exactly once"):
		return
	if not _require(int(ProjectSettings.get_setting("rendering/limits/opengl/max_renderable_lights")) >= fixtures.size(), "Compatibility can discard authored lights before per-room filtering"):
		return
	var contact_lights := 0
	for light: Light3D in fixtures:
		var fixture_extras := light.get_parent().get_meta("extras", {}) as Dictionary
		if not _require(light.light_cull_mask == DAYLIGHT._room_light_mask(fixture_extras) and light.light_cull_mask != 0, "A fixture can consume a different room's light slots"):
			return
		if not _require(light.light_energy > 0.0 and light.light_energy <= 75.0 * DAYLIGHT.DAYTIME_FIXTURE_SCALE and light.top_level, "Fixture energy conversion or scale-free frame is wrong"):
			return
		if light.shadow_enabled:
			contact_lights += 1
			if not _require(light.light_energy <= 75.0 * DAYLIGHT.DAYTIME_FIXTURE_SCALE * DAYLIGHT.SHADOWED_PASS_SCALE, "Shadowed fixture bypasses Compatibility additive-pass calibration"):
				return
			if not _require(light.shadow_caster_mask == DAYLIGHT.FURNITURE_CONTACT_LAYER, "Contact light is shadowing architecture rather than furniture"):
				return
	if not _require(contact_lights > 0 and nest.get_node("CeilingFill").shadow_enabled and nest.get_node("CeilingFill").shadow_caster_mask == DAYLIGHT.FURNITURE_CONTACT_LAYER, "Furniture contact shadow rig is missing"):
		return
	var full_crowns := 0
	var checked_crowns := {}
	for instance: Node in estate.get_children():
		if not instance is MultiMeshInstance3D:
			continue
		if not _require(instance.layers == (1 | DAYLIGHT.LANDSCAPE_LIGHT_LAYER), "Room fixture masks leaked into landscape batches"):
			return
		var rendered := (instance as MultiMeshInstance3D).multimesh.mesh as ArrayMesh
		if not CompleteEstateFinal.is_canopy_mesh(rendered):
			continue
		var source_group := str(instance.get_meta("source_group"))
		if checked_crowns.has(source_group):
			continue
		checked_crowns[source_group] = true
		full_crowns += 1
		var marker := source.find_child(str(instance.get_meta("source_group")), true, false)
		var original := (estate as CompleteEstateFinal)._first_mesh_instance(marker).mesh as ArrayMesh
		var rendered_surfaces: Array = rendered.get("_surfaces")
		var original_surfaces: Array = original.get("_surfaces")
		for index in range(rendered_surfaces.size()):
			if bool(rendered.surface_get_format(index) & Mesh.ARRAY_FORMAT_COLOR):
				var leaf_material := rendered.surface_get_material(index) as ShaderMaterial
				if not _require(leaf_material != null and leaf_material.get_shader_parameter("use_linear_vertex_color"), "Linear glTF leaf colors can be decoded twice"):
					return
			var actual: Dictionary = rendered_surfaces[index]
			var before: Dictionary = original_surfaces[index]
			if not _require(actual.get("lods", []).is_empty() and actual["vertex_data"] == before["vertex_data"] and actual.get("attribute_data") == before.get("attribute_data") and actual["index_data"] == before["index_data"], "Crown still uses generated LOD or base geometry bytes changed"):
				return
	if not _require(full_crowns == 13, "Named and unnamed painted broadleaf crown source groups were not both restored"):
		return
	print("RENDER_FIDELITY full_crowns=", full_crowns, " fixtures=", fixtures.size(), " contact_lights=", contact_lights)
	if not _require(estate.multimesh_instance_count == 216743, "Instanced geometry changed during calibration"):
		return
	var transform_error := str(load("res://scripts/test/test_estate_asset_baseline.gd").batch_transform_error(estate))
	if not _require(transform_error.is_empty(), transform_error):
		return
	if not _require(glazing_modules.size() == 8 and preserved_interior_floors == 1 and naturally_lit_pod_floors == 8, "Eight pod glazing/daylight or accepted ground floor coverage missing"):
		return
	print("PASS: daylight material isolation, shared resources, neutral sun, shadows, sky and complete estate instances; artificial_surfaces=%d sky_surfaces=%d" % [preserved_fixture_emission_count, preserved_sky_count])
	quit(0)


func _mesh(parent: Node, material: Material) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.material = material
	mesh.mesh = box
	parent.add_child(mesh)
	return mesh


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
