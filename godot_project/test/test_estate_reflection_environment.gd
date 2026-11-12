extends SceneTree

const SAMPLE := preload("res://nest/estate/estate_lighting_sample.gd")
const PLACEMENT := preload("res://nest/assembly/glb_placement.gd")
const COVER_LIBRARY := "res://nest/courtyard/parts/ground/courtyard-cover.glb"
const COVERED_COURTYARD := "res://nest/courtyard/overview/courtyard-all/courtyard-covered.scn"

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
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
	var courtyard := (load(COVERED_COURTYARD) as PackedScene).instantiate() as Node3D
	var cover: Node3D
	for placement: Node3D in courtyard.find_children("*", "Node3D", true, false):
		if placement.get_script() == PLACEMENT and placement.library.resource_path == COVER_LIBRARY:
			cover = placement
			break
	if cover == null:
		courtyard.free()
		push_error("The covered courtyard has no placement for its cover")
		quit(1)
		return
	cover.get_parent().remove_child(cover)
	courtyard.free()
	var world := WorldEnvironment.new()
	world.environment = environment
	var fixture := Node3D.new()
	fixture.add_child(cover)
	fixture.add_child(world)
	root.add_child(fixture)
	var error: String = await _check_courtyard_cover(fixture, world)
	fixture.queue_free()
	await process_frame
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	print("PASS reflection environment follows visible day/night background without extra tint or double dimming")
	print("PASS one courtyard cover retains its geometry, changes to the night sky material, and restores its day textures")
	quit(0)


func _check_courtyard_cover(courtyard: Node3D, world: WorldEnvironment) -> String:
	var inner: Array[Dictionary] = []
	var shell: MeshInstance3D
	for mesh: MeshInstance3D in courtyard.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.mesh.get_meta("nest_source_library", "") != COVER_LIBRARY:
			continue
		var material := mesh.get_active_material(0) as BaseMaterial3D
		if material != null and material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			shell = mesh
			continue
		var daytime: Array[Material] = []
		for surface: int in mesh.mesh.get_surface_count():
			daytime.append(mesh.get_active_material(surface))
		inner.append({"node": mesh, "geometry": mesh.mesh, "daytime": daytime})
	if inner.size() != 2 or shell == null or not shell.is_visible_in_tree():
		return "The covered courtyard must use one cover with an inner wall, an inner dome, and a clear shell"

	var optics := SAMPLE.new()
	optics.bind_m01(courtyard)
	for phase: Array in [[1.0, false], [0.0, false], [0.0, true], [1.0, false]]:
		var daylight := float(phase[0])
		var night := is_zero_approx(daylight)
		optics.apply_environment(daylight, night, true, phase[1])
		await process_frame
		for binding: Dictionary in inner:
			var mesh := binding.node as MeshInstance3D
			if not mesh.is_visible_in_tree() or mesh.mesh != binding.geometry:
				return "The same inner cover geometry must stay visible in every phase"
			for surface: int in mesh.mesh.get_surface_count():
				var material := mesh.get_active_material(surface)
				if night:
					if not material is ShaderMaterial or material.shader.resource_path != "res://nest/estate/courtyard_cover_night.gdshader":
						return "Night must draw the sky on the existing cover surfaces"
				elif material != binding.daytime[surface]:
					return "Returning to daylight must restore each original textured cover material"
		if not shell.is_visible_in_tree():
			return "The clear outer shell must stay visible in every phase"
		var sky := world.environment.sky.sky_material as ShaderMaterial
		if not is_equal_approx(float(sky.get_shader_parameter("night_amount")), 1.0 if night else 0.0):
			return "The distant sky outside the cover must follow the same day and night phases"
	return ""
