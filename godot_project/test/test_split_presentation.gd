extends SceneTree
## Exercise the production light and water owners on the actual split assembly.
const LIGHTING := preload("res://nest/rendering/estate_lighting.gd")
const WATER := preload("res://nest/courtyard/parts/waterside/estate_water_display.gd")

func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	if not require(estate.get_meta("split_runtime_ready", false), "Missing complete split presentation bindings"): return
	var control := LIGHTING.new()
	var counts := control.bind(estate)
	if not require(counts.artificial_lights > 200 and counts.ordinary_emission > 100, "Production controls must cover the whole split world"): return
	var rooms := {}
	for light: Light3D in estate.find_children("*", "Light3D", true, false):
		if not LIGHTING.is_ordinary_light(light, estate): continue
		var group := str(LIGHTING.lighting_group(light))
		if group.begins_with("dorm-"): rooms[group] = true
	if not require(rooms.size() == 8, "All eight rooms must have independent light ownership"): return
	control.apply(false, false, PackedStringArray(), true)
	for binding: Dictionary in control._lights:
		if not require(not binding.light.visible and is_zero_approx(binding.light.light_energy), "Daytime switched-off lights remain active"): return
	for binding: Dictionary in control._materials:
		if not require(is_zero_approx(binding.material.emission_energy_multiplier), "Daytime ordinary emission remains active"): return
	control.apply(true, true, PackedStringArray(["dorm-01"]), true)
	var occupied_lights := 0
	for binding: Dictionary in control._lights:
		var group := str(binding.group)
		if group == "dorm-01" and bool(binding.visible):
			occupied_lights += 1
			if not require(binding.light.visible and binding.light.light_energy > 0.0, "Occupied room cannot light up at night"): return
		elif group.begins_with("dorm-"):
			if not require(not binding.light.visible, "Unoccupied room borrowed another shared room's switch"): return
	if not require(occupied_lights > 0, "Occupied-room fixture is missing"): return
	control.apply(true, false, PackedStringArray(), true)
	var evening := []
	for binding: Dictionary in control._lights: evening.append([binding.light.visible, binding.light.light_energy])
	control.apply(false)
	control.apply(true, false, PackedStringArray(), true)
	for index: int in control._lights.size():
		var light: Light3D = control._lights[index].light
		if not require(evening[index] == [light.visible, light.light_energy], "Replay accumulates lamp energy"): return
	var water := WATER.new()
	root.add_child(water)
	water.bind(estate)
	var retired := 0
	for node: Node in estate.find_children("*", "", true, false):
		if not str(node.get_meta("v044_path", "")).begins_with("Generated/ObserverFountainLighting/"): continue
		retired += 1
		if node is Node3D and not require(not node.visible, "Frozen preview effect duplicates live water"): return
		if not require(node.process_mode == Node.PROCESS_MODE_DISABLED, "Frozen preview effects still process beside the live owner"): return
	if not require(retired > 0, "Migration fixture must include the evaluated preview effects"): return
	water.fountain_show.programme = "fixed"
	water.sample(23.0, true)
	var first: float = water.fountain_show.jets[0].get_active_material(0).get_shader_parameter("jet_height")
	water.sample(46.0, true)
	var peak: float = water.fountain_show.jets[0].get_active_material(0).get_shader_parameter("jet_height")
	if not require(peak > 5.8 and not is_equal_approx(first, peak), "Split fountain programme never reaches the real GPU water material"): return
	var lake := estate.find_child("COMPLETE Inset natural lake", true, false) as MeshInstance3D
	var lake_material := lake.get_active_material(0) as ShaderMaterial
	water.sample(8.0, false)
	var before: float = lake_material.get_shader_parameter("presentation_time")
	water.sample(9.0, false)
	if not require(float(lake_material.get_shader_parameter("presentation_time")) > before, "Split lake animation is frozen"): return
	water.set_component_paused("fountain", true)
	if not require(not water.get_node("WaterfallLandingSplash").emitting, "Paused split water keeps emitting particles"): return
	water.set_component_paused("fountain", false)
	if not require(water.get_node("WaterfallLandingSplash").emitting, "Split waterfall particles cannot resume"): return
	water.set_presentation_paused(true)
	var frozen := water.presentation_seconds()
	await process_frame
	await process_frame
	if not require(water.presentation_seconds() == frozen and not water.is_processing(), "Whole-world pause must freeze presentation time and updates"): return
	water.set_presentation_paused(false)
	print("PASS split presentation: eight independent room switches, day/night emission, replay, live fountain/lake materials and particle pause/resume")
	water.free(); estate.free(); quit()
