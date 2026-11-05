extends SceneTree

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var display := preload("res://rooms/estate/estate_water_display.gd").new()
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
