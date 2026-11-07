extends SceneTree

const SAMPLE := preload("res://nest/estate/estate_lighting_sample.gd")

func _initialize() -> void:
	var nest := load("res://nest/nest.tscn") as PackedScene
	var state := nest.get_state()
	var environment: Environment
	for node in range(state.get_node_count()):
		if state.get_node_name(node) != &"WorldEnvironment": continue
		for property in range(state.get_node_property_count(node)):
			if state.get_node_property_name(node, property) == &"environment":
				environment = state.get_node_property_value(node, property).duplicate(true)
	var sample := SAMPLE.new()
	var original_background := environment.background_mode
	var original_ambient := environment.ambient_light_energy
	if environment.ambient_light_source != Environment.AMBIENT_SOURCE_COLOR or not is_equal_approx(original_ambient, 0.2291831181):
		push_error("The authored daytime environment diffuse must survive nighttime lighting changes")
		quit(1)
		return
	sample.bind_environment(environment)
	for phase: Array in [[1.0,false], [0.0,false], [0.0,true], [1.0,false]]:
		var daylight := float(phase[0])
		sample.apply_environment(daylight, is_zero_approx(daylight), true, phase[1])
		var sky := environment.sky.sky_material as ShaderMaterial
		var reflected: Variant = sky.get_shader_parameter("environment_color")
		var night := is_zero_approx(daylight)
		if environment.ambient_light_source != (Environment.AMBIENT_SOURCE_DISABLED if night else Environment.AMBIENT_SOURCE_COLOR):
			push_error("Day must restore environment diffuse; evening and quiet night must disable it")
			quit(1)
			return
		var night_amount: Variant = sky.get_shader_parameter("night_amount")
		if night_amount == null or not is_equal_approx(float(night_amount), 1.0 if night else 0.0):
			push_error("Night sky must enable its gradient and sparse stars only at night")
			quit(1)
			return
		if environment.background_mode != (Environment.BG_SKY if night else original_background):
			push_error("Night stars must be visible, and returning to day must restore the approved background")
			quit(1)
			return
		if not is_equal_approx(environment.ambient_light_energy, original_ambient * (SAMPLE.NIGHT_NATURAL_SCALE if night else 1.0)):
			push_error("The visible night sky must not increase ambient lighting")
			quit(1)
			return
		if reflected == null or not (reflected as Color).is_equal_approx(environment.background_color):
			push_error("Reflections must use the displayed environment color in both day and night")
			quit(1)
			return
		if not is_equal_approx(environment.background_energy_multiplier, 1.0):
			push_error("The night environment color must not be dimmed a second time")
			quit(1)
			return
		if not is_equal_approx(environment.tonemap_exposure, 0.88):
			push_error("Reflection repair must preserve exposure")
			quit(1)
			return
	print("PASS reflection environment follows visible day/night background without extra tint or double dimming")
	quit(0)
