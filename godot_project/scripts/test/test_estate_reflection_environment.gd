extends SceneTree

const SAMPLE := preload("res://rooms/estate/estate_lighting_sample.gd")

func _initialize() -> void:
	var nest := load("res://rooms/nest.tscn") as PackedScene
	var state := nest.get_state()
	var environment: Environment
	for node in range(state.get_node_count()):
		if state.get_node_name(node) != &"WorldEnvironment": continue
		for property in range(state.get_node_property_count(node)):
			if state.get_node_property_name(node, property) == &"environment":
				environment = state.get_node_property_value(node, property).duplicate(true)
	var sample := SAMPLE.new()
	sample.bind_environment(environment)
	for daylight in [1.0, 0.0, 1.0]:
		sample.apply_environment(daylight, is_zero_approx(daylight))
		var sky := environment.sky.sky_material as ShaderMaterial
		var reflected: Variant = sky.get_shader_parameter("environment_color")
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
