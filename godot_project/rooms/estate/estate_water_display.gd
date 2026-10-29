extends Node3D
## Shared water presentation; callers supply the night state, never world time.

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const COLORS := [Color(0.12, 0.65, 0.85), Color(0.20, 0.30, 0.90), Color(0.55, 0.25, 0.75)]
var lake: MeshInstance3D
var fountain_materials: Array[ShaderMaterial] = []
var _day_lights: Array[Dictionary] = []
var _sky: Array[Dictionary] = []
var _environment: Environment
var _day_environment: Dictionary = {}
var _lamp: OmniLight3D
var fountain_rings: Array[Dictionary] = []
var night_enabled := false
var _manage_environment := true
var _seconds := 0.0

func bind(geometry: Node3D, environment: Environment, manage_environment: bool = true) -> void:
	_manage_environment = manage_environment
	set_process(not manage_environment)
	_environment = environment
	for key: String in ["background_color", "ambient_light_energy", "background_energy_multiplier"]:
		_day_environment[key] = environment.get(key)
	for light: DirectionalLight3D in geometry.find_children("*", "DirectionalLight3D", true, false):
		_day_lights.append({"light": light, "energy": light.light_energy})
	var pool: MeshInstance3D
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		if str(mesh.name) == "Reference fountain water":
			pool = mesh
		if str(mesh.name) == "COMPLETE Inset natural lake":
			lake = mesh
		if mesh.mesh != null:
			for surface in range(mesh.mesh.get_surface_count()):
				var material := mesh.get_active_material(surface)
				if material != null and DAYLIGHT._is_background(material.resource_name.to_lower()):
					_sky.append({"mesh": mesh, "visible": mesh.visible})
					break
	assert(pool != null and lake != null, "Water review needs the authored pool and entire lake")
	var lake_material := lake.get_active_material(0) as ShaderMaterial
	lake_material.set_shader_parameter("wave_amplitude", 0.04)
	lake_material.set_shader_parameter("detail_amplitude", 0.012)
	lake_material.set_shader_parameter("accent_strength", 0.0)
	var pool_bounds := pool.global_transform * pool.get_aabb()
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		var center := (mesh.global_transform * mesh.get_aabb()).get_center()
		if center.x < pool_bounds.position.x or center.x > pool_bounds.end.x or center.z < pool_bounds.position.z or center.z > pool_bounds.end.z:
			continue
		for surface in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material != null and material.get_meta("estate_water_role", "") in ["surface", "jet", "ripple"]:
				fountain_materials.append(material)
				if material.get_meta("estate_water_role", "") == "ripple":
					var bounds := mesh.global_transform * mesh.get_aabb()
					fountain_rings.append({"material":material,"radius":maxf(bounds.size.x,bounds.size.z)*0.5})
	_lamp = OmniLight3D.new()
	_lamp.name = "LocalFountainColorLight"
	_lamp.omni_range = 6.0
	_lamp.shadow_enabled = false
	_lamp.light_cull_mask = DAYLIGHT.OUTDOOR_LIGHT_LAYER | DAYLIGHT.WATER_LIGHT_LAYER
	add_child(_lamp)
	_lamp.global_position = pool_bounds.get_center() + Vector3.UP * 0.35
	fountain_rings.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return float(a["radius"])<float(b["radius"]))
	sample(0.0, false)

func sample(seconds: float, night: bool) -> void:
	var phase := fposmod(seconds, 24.0) / 8.0
	var index := int(phase)
	var color: Color = COLORS[index].lerp(COLORS[(index + 1) % COLORS.size()], smoothstep(0.0, 1.0, phase - index))
	# A subdued accent on the existing lake surface, without added beams or stripes.
	var lake_material := lake.get_active_material(0) as ShaderMaterial
	lake_material.set_shader_parameter("accent_color",Vector3(color.r,color.g,color.b))
	lake_material.set_shader_parameter("accent_strength",0.15 if night else 0.0)
	# Light only the original fountain water, never a free-standing beam.
	for material: ShaderMaterial in fountain_materials:
		material.set_shader_parameter("accent_color", Vector3(color.r, color.g, color.b))
		var strength := 1.4 if material.get_meta("estate_water_role", "")=="jet" else 0.35
		material.set_shader_parameter("accent_strength", strength if night else 0.0)
	# Each actual pool ring peaks later than the smaller one, then fades.
	var cycle := fposmod(seconds,5.0)
	for ring_index in range(fountain_rings.size()):
		var material := fountain_rings[ring_index]["material"] as ShaderMaterial
		var distance := (cycle-(0.55+float(ring_index)*0.7))/0.33
		var pulse := exp(-distance*distance)
		material.set_shader_parameter("accent_strength",0.04+1.8*pulse if night else 0.0)
	_lamp.visible = night
	_lamp.light_color = color
	_lamp.light_energy = 0.6 if night else 0.0
	if not _manage_environment: return
	for binding: Dictionary in _day_lights:
		(binding["light"] as DirectionalLight3D).light_energy = float(binding["energy"]) * (0.045 if night else 1.0)
	for binding: Dictionary in _sky:
		(binding["mesh"] as MeshInstance3D).visible = bool(binding["visible"]) and not night
	_environment.background_color = Color(0.015, 0.025, 0.05) if night else _day_environment["background_color"]
	_environment.ambient_light_energy = 0.08 if night else float(_day_environment["ambient_light_energy"])
	_environment.background_energy_multiplier = 0.2 if night else float(_day_environment["background_energy_multiplier"])


func set_night(value: bool) -> void:
	night_enabled = value
	sample(_seconds, night_enabled)


func _process(delta: float) -> void:
	if not is_visible_in_tree(): return
	_seconds += delta
	sample(_seconds, night_enabled)
