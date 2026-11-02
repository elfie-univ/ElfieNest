extends SceneTree

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const CONTROL := preload("res://rooms/estate/estate_lighting.gd")
const SAMPLE := preload("res://rooms/estate/estate_lighting_sample.gd")
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var geometry := load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate() as Node3D
	root.add_child(geometry)
	DAYLIGHT.apply(geometry)
	var roof_meshes: Array[MeshInstance3D] = []
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if str(extras.get("module", "")) != "central" or int(extras.get("floor", 1)) != 4: continue
		roof_meshes.append(mesh)
		check(str(CONTROL.lighting_group(mesh)).trim_prefix("safety:") == "central-04", "Roof fixtures must not share the third-floor switch")
		for surface in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface) as BaseMaterial3D
			if material == null or not material.emission_enabled: continue
			var original := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
			if original.resource_name in ["Roof01 radial luminous crystal", "Roof lighting single broad tapered cyan leaf vein inside"]:
				check(material.emission_texture == original.emission_texture and material.albedo_texture == original.albedo_texture, "Roof night calibration must preserve the actual radial and leaf textures")
				for quiet in [false, true]:
					check(CONTROL.emission_energy(material, original.emission_energy_multiplier, &"central-04", quiet) < original.emission_energy_multiplier, "Textured roof emission must retain contrast in both night periods")
	var roof_lights: Array[Light3D] = []
	for light: Light3D in geometry.find_children("*", "Light3D", true, false):
		if CONTROL.lighting_group(light) == &"central-04" and CONTROL.is_ordinary_light(light, geometry): roof_lights.append(light)
	var designed_sources := 0
	for mesh in roof_meshes:
		designed_sources += ((mesh.get_meta("extras", {}) as Dictionary).get("design_lights", []) as Array).size()
	check(roof_lights.size() == designed_sources, "Roof must not gain unregistered fill lights to compensate for luminous-only surfaces")
	var third_mask := DAYLIGHT._activity_light_mask({"floor": 3}) | DAYLIGHT._room_light_mask({"module": "central", "floor": 3})
	for light in roof_lights:
		check((light.light_cull_mask & third_mask) == 0, "Roof lamps must not light the third floor")
		check(is_zero_approx(light.light_specular), "Roof diffuse coverage must not create white point reflections")
		check(roof_meshes.any(func(mesh: MeshInstance3D) -> bool: return (mesh.layers & light.light_cull_mask) != 0 and str(mesh.name).begins_with("Roof01 petal")), "Roof light must reach the actual petal shells")
		check(roof_meshes.any(func(mesh: MeshInstance3D) -> bool: return (mesh.layers & light.light_cull_mask) != 0 and str(mesh.name).begins_with("Central L4 round arrival floor")), "Roof light must reach the actual walking floor")
	var sample := SAMPLE.new()
	sample.bind_m01(geometry)
	sample.apply_environment(0.0, true)
	for light in roof_lights: check(light.visible and light.light_energy > 0.0, "Roof lamps must illuminate the evening scene")
	sample.apply_environment(1.0, false)
	for light in roof_lights: check(not light.visible, "Roof lamps must turn off with daytime ordinary lighting")
	sample.apply_environment(0.0, true, true, true, PackedStringArray(["central-03"]), true)
	for light in roof_lights: check(not light.visible, "Third-floor occupancy must not switch on the roof at quiet hours")
	sample.apply_environment(0.0, true, true, true, PackedStringArray(["central-04"]), true)
	for light in roof_lights: check(light.visible, "Roof occupancy must switch on roof lighting at quiet hours")
	check(not roof_meshes.is_empty(), "The test must exercise the real fourth-floor asset")
	geometry.free()
	for message in failures: push_error(message)
	if failures.is_empty(): print("PASS roof emission preservation, designed sources only and floor isolation")
	quit(0 if failures.is_empty() else 1)
