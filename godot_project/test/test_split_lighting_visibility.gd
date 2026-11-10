extends SceneTree

const CONTROL := preload("res://nest/estate/estate_lighting.gd")
const RUNTIME := preload("res://nest/assembly/estate_runtime.gd")
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var lamps: Array[Dictionary] = []
	for light: Light3D in estate.find_children("*", "Light3D", true, false):
		if not str(light.name).begins_with("BedroomCeilingM"): continue
		check(bool(light.get_meta(CONTROL.INITIAL_VISIBLE, false)), "Saved ceiling must be available: " + str(light.name))
		check(bool(light.get_meta("estate_fixture_calibrated", false)), "Saved ceiling must retain calibration")
		lamps.append({"light":light, "color":light.light_color, "range":(light as OmniLight3D).omni_range, "attenuation":(light as OmniLight3D).omni_attenuation, "shadow":light.shadow_enabled, "specular":light.light_specular, "boost":CONTROL.light_boost(light, &"dorm-01")})
	check(lamps.size() == 8, "The split estate must retain eight bedroom ceiling lights")
	var control := CONTROL.new()
	control.bind(estate)
	control.apply(false)
	for entry: Dictionary in lamps:
		check(not entry.light.visible, "Day must keep bedroom ceilings off")
	control.apply(true)
	for entry: Dictionary in lamps:
		var light := entry.light as OmniLight3D
		check(light.visible, "Evening must enable the saved ceiling: " + str(light.name))
		check(is_equal_approx(light.light_energy, 8.0 / PI), "Evening must retain calibrated output without generic boost")
		check(light.light_color == entry.color and light.omni_range == entry.range and light.omni_attenuation == entry.attenuation, "Restore must preserve saved color and range calibration")
		check(light.shadow_enabled == entry.shadow and light.light_specular == entry.specular and CONTROL.light_boost(light, CONTROL.lighting_group(light)) == entry.boost, "Restore must preserve shadows, specular and boost")
	control.apply(true, true, PackedStringArray(["dorm-01"]), true)
	for entry: Dictionary in lamps:
		check(entry.light.visible == (CONTROL.lighting_group(entry.light) == &"dorm-01"), "Quiet hours must enable only the occupied bedroom")
	control.apply(false)
	control.apply(true)
	for entry: Dictionary in lamps:
		check(entry.light.visible, "Day/night repetition must not erase authored availability")
	estate.free()
	check_visibility_fallback()
	for message: String in failures: push_error(message)
	if failures.is_empty(): print("PASS split ceiling availability and saved calibration")
	quit(0 if failures.is_empty() else 1)

func check_visibility_fallback() -> void:
	var fixture := RUNTIME.new()
	var controls := {"lights":{}, "emission":{}}
	for label: String in ["Available", "Disabled", "Untagged"]:
		var light := OmniLight3D.new()
		light.name = label
		fixture.add_child(light)
		if label != "Untagged": light.set_meta(CONTROL.INITIAL_VISIBLE, label == "Available")
		controls.lights[label] = {"energy":1.0, "mask":256, "group":"dorm-01", "visible":label == "Disabled"}
	fixture.restore_lighting(controls)
	fixture.restore_lighting(controls)
	check(bool(fixture.get_node("Available").get_meta(CONTROL.INITIAL_VISIBLE)), "Day snapshot must not disable an authored available light")
	check(not bool(fixture.get_node("Disabled").get_meta(CONTROL.INITIAL_VISIBLE)), "Visible snapshot must not enable an authored disabled light")
	check(not bool(fixture.get_node("Untagged").get_meta(CONTROL.INITIAL_VISIBLE)), "Untagged lights must retain the snapshot fallback")
	fixture.free()
