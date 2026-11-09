extends SceneTree

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	if not check_split_ground_clearance(estate): return
	var display := preload("res://nest/estate/estate_water_display.gd").new()
	root.add_child(display)
	display.bind(estate,Environment.new(),false)
	var channel := estate.find_child("COMPLETE Short east spillway",true,false) as MeshInstance3D
	var shallow := channel.get_active_material(0) as ShaderMaterial
	var opacity: Variant = shallow.get_shader_parameter("water_opacity")
	if not require(opacity is float and opacity >= 0.5 and opacity < 0.8, "Channel needs tinted half-transparent water, not nearly clear glass; opacity=" + str(opacity) + " shader=" + shallow.shader.resource_path): return
	var curtain := estate.find_child("Continuous shallow waterfall from solid spillway crest",true,false) as MeshInstance3D
	var water := curtain.get_active_material(0) as ShaderMaterial
	if not require(water.shader.resource_path.ends_with("estate_waterfall.gdshader"), "Only the actual waterfall should use the turbulent curtain finish"): return
	var landing: MeshInstance3D
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		var material := mesh.get_active_material(0) as ShaderMaterial
		if material != null and material.shader.resource_path.ends_with("estate_waterfall_foam.gdshader"): landing = mesh
	if not require(landing != null, "Use a continuous white landing-foam surface, not only round droplets"): return
	var splash := display.get_node("WaterfallLandingSplash") as CPUParticles3D
	if not require(splash.mesh is QuadMesh and splash.mesh.material is BaseMaterial3D and splash.mesh.material.albedo_texture != null, "Secondary spray must be soft mist sprites rather than spheres"): return
	var foam := landing.get_active_material(0) as ShaderMaterial
	if not require((landing.global_transform * landing.get_aabb()).size.z >= (curtain.global_transform * curtain.get_aabb()).size.z, "Landing foam must span the real water curtain"): return
	var lake := estate.find_child("COMPLETE Inset natural lake",true,false) as MeshInstance3D
	var lake_level := (lake.global_transform * lake.get_aabb()).end.y
	var contact_x := -INF
	for point: Vector3 in curtain.mesh.get_faces():
		var world := curtain.global_transform * point
		if absf(world.y-lake_level) < 0.002: contact_x = maxf(contact_x,world.x)
	if not require(not is_inf(contact_x), "The waterfall must actually meet the lake surface"): return
	var foam_bounds := landing.global_transform * landing.get_aabb()
	if not require(absf(foam_bounds.get_center().x-contact_x) <= 0.12 and foam_bounds.position.x <= contact_x and foam_bounds.end.x > contact_x + 0.2, "Foam must straddle the real waterfall/lake contact, not float downstream"): return
	if not require(absf(splash.global_position.x-contact_x) < 0.02, "Mist must originate at the real water impact"): return
	var half_height: float = (splash.mesh as QuadMesh).size.y * 0.5 * splash.scale_amount_max
	var minimum_height := splash.global_position.y - lake_level - splash.emission_box_extents.y - half_height
	var minimum_upward_speed := splash.initial_velocity_min * cos(deg_to_rad(splash.spread))
	var final_height := minimum_upward_speed * splash.lifetime + 0.5 * splash.gravity.y * splash.lifetime * splash.lifetime
	if not require(minimum_height >= 0.004 and minimum_height + minf(final_height, 0.0) >= 0.004, "Mist sprites must stay above the lake through their upward splash"): return
	if not require(splash.amount >= 48 and minimum_upward_speed >= 0.25, "Impact spray must visibly rise from the water"): return
	display.sample(0.0,true)
	var foam_night: Variant = foam.get_shader_parameter("night_visibility")
	if not require(foam_night is float and float(foam_night) >= 0.8, "White impact foam must remain visible at night"): return
	if not require(float(water.get_shader_parameter("waterfall_glow")) >= 1.2, "The waterfall sheet needs visible, soft night illumination"): return
	display.sample(0.0,false)
	if not require(is_zero_approx(float(foam.get_shader_parameter("night_visibility"))) and is_zero_approx(float(water.get_shader_parameter("waterfall_glow"))), "Added night brightness must turn off during daytime"): return
	for material: ShaderMaterial in [shallow, water, foam]:
		if not require(not material.shader.get_shader_uniform_list().is_empty(), "Water finish shader did not compile"): return
	display.sample(1.0,false)
	var phase: float = water.get_shader_parameter("waterfall_phase")
	display.sample(2.0,false)
	if not require(float(water.get_shader_parameter("waterfall_phase")) != phase, "Water curtain must flow"): return
	display.set_component_paused("fountain",true)
	display.sample(3.0,false)
	phase = water.get_shader_parameter("waterfall_phase")
	var foam_time: float = foam.get_shader_parameter("presentation_time")
	display.sample(4.0,false)
	if not require(is_equal_approx(phase,float(water.get_shader_parameter("waterfall_phase"))) and is_equal_approx(foam_time,float(foam.get_shader_parameter("presentation_time"))) and not splash.emitting, "Waterfall, foam and mist must pause with the existing fountain control"): return
	display.set_component_paused("fountain",false)
	if not require(splash.emitting, "Waterfall mist must resume"): return
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.fov = 12.0
	var target := (curtain.global_transform * curtain.get_aabb()).get_center()
	camera.global_position = target + Vector3(0,1.2,-3.0)
	camera.look_at(target)
	camera.make_current()
	if not require(not display.fountain_show.visible_from(camera), "Near-waterfall fixture must exclude the main fountain"): return
	display.refresh_visibility()
	if not require(display.is_processing(), "A close-up of the waterfall must keep its water and foam moving even when the fountain is off screen"): return
	print("PASS: tinted channel, turbulent waterfall, full-width white foam and soft spray preserve pause/resume")
	camera.free()
	display.free()
	estate.free()
	quit(0)

func check_split_ground_clearance(estate: Node3D) -> bool:
	var grounds: Array[MeshInstance3D] = []
	var sources := {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.has_meta("source_geometry_path"): continue
		var extras: Dictionary = mesh.get_meta("extras", {})
		var source := str(extras.get("source_name", ""))
		if not source.begins_with("COMPLETE Building garden island"): continue
		grounds.append(mesh)
		sources[source] = true
	if not require(sources.size() == 4, "Retain the four approved split ground islands"): return false
	var shore := preload("res://test/split_estate_test_support.gd").shore_geometry(estate)
	var center: Vector2 = shore.water_bounds.get_center()
	if not require(Geometry2D.is_point_in_polygon(center, shore.water), "Lake measurement point must lie inside actual water geometry"): return false
	var center_occlusion := 0
	var bank_contacts := 0
	var measured_faces := 0
	for ground: MeshInstance3D in grounds:
		var faces := ground.mesh.get_faces()
		for start: int in range(0, faces.size(), 3):
			var a := ground.global_transform * faces[start]
			var b := ground.global_transform * faces[start + 1]
			var c := ground.global_transform * faces[start + 2]
			if not require(a.is_finite() and b.is_finite() and c.is_finite(), "Split ground contains nonfinite geometry"): return false
			measured_faces += 1
			var height := _ground_height_at(center, a, b, c)
			if is_finite(height) and height > shore.water_height + 0.015: center_occlusion += 1
			for index: int in range(0, shore.water.size(), maxi(1, shore.water.size() / 16)):
				var edge: Vector2 = shore.water[index]
				var outward := edge + (edge - center).normalized() * 0.5
				var bank_height := _ground_height_at(outward, a, b, c)
				if is_finite(bank_height) and bank_height > shore.water_height: bank_contacts += 1
	print("SPLIT_GROUND_CLEARANCE sources=", sources.size(), " world_faces=", measured_faces, " lake_center_occlusion=", center_occlusion, " bank_contacts=", bank_contacts)
	return require(center_occlusion == 0 and bank_contacts > 0, "Placed ground must surround the real lake without covering its interior")

func _ground_height_at(point: Vector2, a: Vector3, b: Vector3, c: Vector3) -> float:
	var denominator := (b.z-c.z)*(a.x-c.x)+(c.x-b.x)*(a.z-c.z)
	if absf(denominator) < 0.0000000001: return NAN
	var u := ((b.z-c.z)*(point.x-c.x)+(c.x-b.x)*(point.y-c.z))/denominator
	var v := ((c.z-a.z)*(point.x-c.x)+(a.x-c.x)*(point.y-c.z))/denominator
	if minf(u, minf(v, 1.0-u-v)) < -0.000001: return NAN
	return u*a.y+v*b.y+(1.0-u-v)*c.y
