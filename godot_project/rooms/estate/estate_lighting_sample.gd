extends RefCounted
## Explicit optical-review control, never a clock or a world-state authority.
## Callers bind owned sample resources and supply the reviewed daylight level.

const ESTATE_LIGHTING := preload("res://rooms/estate/estate_lighting.gd")
const NIGHT_NATURAL_SCALE := ESTATE_LIGHTING.DAYLIGHT.NIGHT_NATURAL_SCALE
var _lights: Dictionary = {}
var _emission: Dictionary = {}
var _natural_materials: Array[ShaderMaterial] = []
var _environments: Dictionary = {}
var _sky_geometry: Array[Dictionary] = []


func bind_light(light: Light3D, group: StringName) -> void:
	var identity := light.get_instance_id()
	if not _lights.has(identity):
		_lights[identity] = {"light": light, "group": group, "energy": light.get_meta("estate_initial_energy",light.light_energy), "visible": light.get_meta(ESTATE_LIGHTING.INITIAL_VISIBLE,light.visible)}


func bind_emission(material: BaseMaterial3D, group: StringName) -> void:
	var identity := material.get_instance_id()
	if not _emission.has(identity):
		_emission[identity] = {"material": material, "group": group, "energy": material.get_meta(ESTATE_LIGHTING.INITIAL_EMISSION,material.emission_energy_multiplier)}


func bind_natural_material(material: ShaderMaterial) -> void:
	if material not in _natural_materials:
		_natural_materials.append(material)


func bind_environment(environment: Environment) -> void:
	var identity := environment.get_instance_id()
	if not _environments.has(identity):
		_environments[identity] = {"environment": environment, "ambient": environment.ambient_light_energy, "background": environment.background_color, "sky": environment.background_energy_multiplier}


func apply_sample(daylight: float, room_in_use: bool = true, ordinary_enabled: bool = true) -> void:
	# Reviewed comparisons follow the existing night-only ordinary-light rule.
	apply_environment(daylight, ordinary_enabled and is_zero_approx(daylight), room_in_use)


func apply_environment(daylight: float, lights_on: bool, room_in_use: bool = true, quiet_mode: bool = false, occupied: PackedStringArray = PackedStringArray(), usage_known: bool = false) -> void:
	var level := clampf(daylight, 0.0, 1.0)
	var natural := lerpf(NIGHT_NATURAL_SCALE, 1.0, level)
	# Production consumes Nest's explicit ordinary-light state, including overrides.
	var artificial := 1.0 if lights_on else 0.0
	for binding: Dictionary in _lights.values():
		var light := binding["light"] as Light3D
		var group: StringName = binding.group
		var scale := _group_scale(group,natural,artificial,room_in_use) if group in [&"natural",&"path",&"status"] else ESTATE_LIGHTING.group_scale(group,lights_on,quiet_mode,occupied,usage_known)
		if group not in [&"natural",&"path",&"status",&"outdoor"] and not room_in_use: scale=0.0
		if level<1.0 and group!=&"natural": scale*=ESTATE_LIGHTING.light_boost(light, group, quiet_mode)
		light.light_energy = float(binding["energy"]) * scale
		light.visible = bool(binding["visible"]) and scale > 0.0
	for binding: Dictionary in _emission.values():
		var material := binding["material"] as BaseMaterial3D
		var group: StringName = binding.group
		var scale := _group_scale(group,natural,artificial,room_in_use) if group in [&"natural",&"path",&"status"] else ESTATE_LIGHTING.group_scale(group,lights_on,quiet_mode,occupied,usage_known)
		if group not in [&"natural",&"path",&"status",&"outdoor"] and not room_in_use: scale=0.0
		var energy := ESTATE_LIGHTING.emission_energy(material, binding["energy"], group, quiet_mode) if level<1.0 else float(binding["energy"])
		material.emission_energy_multiplier = energy * scale
	for material: ShaderMaterial in _natural_materials:
		material.set_shader_parameter("natural_light_scale", natural)
	for sky: Dictionary in _sky_geometry:
		(sky["mesh"] as MeshInstance3D).visible = bool(sky["visible"]) and level > 0.0
	for binding: Dictionary in _environments.values():
		var environment := binding["environment"] as Environment
		environment.ambient_light_energy = float(binding["ambient"]) * natural
		environment.background_color = Color(0.015, 0.025, 0.05) if is_zero_approx(level) else ((binding["background"] as Color).srgb_to_linear() * natural).linear_to_srgb()
		# Compatibility uses this multiplier both in panorama generation and
		# reflection sampling. Keep the total radiance scale equal to natural.
		environment.background_energy_multiplier = float(binding["sky"]) * sqrt(natural)


func bind_m01(sample: Node3D) -> Dictionary:
	var counts := {"room_lights": 0, "natural_lights": 0, "ordinary_surfaces": 0, "natural_surfaces": 0, "preserved_emissive_surfaces": 0}
	for light: Light3D in sample.find_children("*", "Light3D", true, false):
		var natural := light is DirectionalLight3D and not ESTATE_LIGHTING.is_ordinary_light(light, sample)
		var group := &"natural" if natural else ESTATE_LIGHTING.lighting_group(light)
		bind_light(light, group)
		counts["natural_lights" if group == &"natural" else "room_lights"] += 1
	for world: WorldEnvironment in sample.find_children("*", "WorldEnvironment", true, false):
		# Own the environment and its sky; never dim a shared source resource.
		world.environment = world.environment.duplicate(true)
		bind_environment(world.environment)
	var owned: Dictionary = {}
	for mesh: MeshInstance3D in sample.find_children("*", "MeshInstance3D", true, false):
		for surface in range(mesh.mesh.get_surface_count()):
			var original := mesh.get_active_material(surface)
			if original == null:
				continue
			if ESTATE_LIGHTING.DAYLIGHT._is_background(original.resource_name.to_lower()):
				if not _sky_geometry.any(func(entry: Dictionary) -> bool: return entry["mesh"] == mesh):
					_sky_geometry.append({"mesh": mesh, "visible": mesh.visible})
				continue
			var group := ESTATE_LIGHTING.lighting_group(mesh)
			var identity := "%d:%s"%[original.get_instance_id(),group]
			if not owned.has(identity):
				var material := original.duplicate() as Material
				owned[identity] = material
				if material is ShaderMaterial:
					bind_natural_material(material)
					counts["natural_surfaces"] += 1
				elif material is BaseMaterial3D and (material as BaseMaterial3D).emission_enabled:
					if ESTATE_LIGHTING.is_ordinary_emission(material):
						bind_emission(material, group)
						counts["ordinary_surfaces"] += 1
					else:
						# Screen content keeps its source emission; guides are ordinary lights.
						# This sample does not invent their operational state.
						counts["preserved_emissive_surfaces"] += 1
			mesh.set_surface_override_material(surface, owned[identity])
	return counts


static func _group_scale(group: StringName, natural: float, artificial: float, room_in_use: bool) -> float:
	match group:
		&"natural":
			return natural
		&"room":
			return artificial if room_in_use else 0.0
		&"path":
			return artificial
		&"status":
			return 1.0
	push_error("Unknown sample lighting group: %s" % group)
	return 0.0
