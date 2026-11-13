extends RefCounted
## Explicit optical-review control, never a clock or a world-state authority.
## Callers bind owned sample resources and supply the reviewed daylight level.

const ESTATE_LIGHTING := preload("res://nest/rendering/estate_lighting.gd")
const RENDER_BATCHES := preload("res://nest/rendering/estate_instance_batches.gd")
const REFLECTION_SKY := preload("res://nest/rendering/estate_reflection_sky.gdshader")
const COURTYARD_COVER := "res://nest/courtyard/parts/ground/courtyard-cover.glb"
const COURTYARD_NIGHT := preload("res://nest/courtyard/parts/ground/courtyard_cover_night.gdshader")
# Project the original sky from the ring-road eye point onto both cover surfaces.
const COURTYARD_SKY_ORIGIN := Vector3(0.0, 3.4, 22.0)
const NIGHT_NATURAL_SCALE := ESTATE_LIGHTING.DAYLIGHT.NIGHT_NATURAL_SCALE
var _lights: Dictionary = {}
var _emission: Dictionary = {}
var _natural_materials: Array[ShaderMaterial] = []
var _environments: Dictionary = {}
var _courtyard_cover: Array[Dictionary] = []
var _opaque_bindings: Array[Dictionary] = []
var _unshared_opaque: Dictionary = {}


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
		_environments[identity] = {"environment": environment, "ambient": environment.ambient_light_energy, "ambient_source": environment.ambient_light_source, "background": environment.background_color, "background_mode": environment.background_mode, "sky": environment.background_energy_multiplier}


func apply_sample(daylight: float, room_in_use: bool = true, ordinary_enabled: bool = true) -> void:
	# Reviewed comparisons follow the existing night-only ordinary-light rule.
	apply_environment(daylight, ordinary_enabled and is_zero_approx(daylight), room_in_use)


func apply_environment(daylight: float, lights_on: bool, room_in_use: bool = true, quiet_mode: bool = false, occupied: PackedStringArray = PackedStringArray(), usage_known: bool = false) -> void:
	var level := clampf(daylight, 0.0, 1.0)
	var night := is_zero_approx(level)
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
	for binding: Dictionary in _courtyard_cover:
		var mesh := binding.mesh as MeshInstance3D
		var material: Material = binding.night if night else binding.day
		if mesh.material_override != material:
			mesh.material_override = material
	for binding: Dictionary in _environments.values():
		var environment := binding["environment"] as Environment
		# Preserve the authored daytime environment diffuse, separately from
		# mounted fixtures. Night must not inherit daytime environment lighting.
		environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED if night else int(binding["ambient_source"]) as Environment.AmbientSource
		environment.ambient_light_energy = float(binding["ambient"]) * level
		environment.background_color = Color(0.015, 0.025, 0.05) if night else ((binding["background"] as Color).srgb_to_linear() * natural).linear_to_srgb()
		# Compatibility uses this multiplier both in panorama generation and
		# reflection sampling. Keep the total radiance scale equal to natural.
		var sky_energy := float(binding["sky"]) * sqrt(natural)
		if environment.sky != null:
			var sky_material := environment.sky.sky_material as ShaderMaterial
			if sky_material != null and sky_material.shader == REFLECTION_SKY:
				environment.background_mode = Environment.BG_SKY if night else int(binding["background_mode"]) as Environment.BGMode
				var backdrop_night := 1.0 if night else 0.0
				var night_amount: Variant = sky_material.get_shader_parameter("night_amount")
				if night_amount == null or not is_equal_approx(float(night_amount), backdrop_night):
					sky_material.set_shader_parameter("night_amount", backdrop_night)
				# Night already has its own dim background color. Do not apply
				# the old studio-panorama attenuation to it a second time.
				if sky_material.get_shader_parameter("environment_color") != environment.background_color:
					sky_material.set_shader_parameter("environment_color", environment.background_color)
				sky_energy = 1.0
		if not is_equal_approx(environment.background_energy_multiplier, sky_energy):
			environment.background_energy_multiplier = sky_energy


func _bind_courtyard_cover(mesh: MeshInstance3D, projection_origin: Vector3) -> bool:
	var source := mesh.get_active_material(0)
	if source == null or not ESTATE_LIGHTING.DAYLIGHT._is_background(source.resource_name.to_lower()):
		return false
	var material := ShaderMaterial.new()
	material.shader = COURTYARD_NIGHT
	material.set_shader_parameter("dome", source.resource_name.ends_with(" dome"))
	material.set_shader_parameter("projection_origin", projection_origin)
	# Preserve any authored surface overrides for the exact daytime appearance.
	_courtyard_cover.append({"mesh": mesh, "day": mesh.material_override, "night": material})
	return true


func bind_m01(sample: Node3D) -> Dictionary:
	RENDER_BATCHES.restore_before_write(sample, true)
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
	var opaque_inputs: Dictionary = {}
	var opaque_sources: Dictionary = {}
	var sky_origin := sample.to_global(COURTYARD_SKY_ORIGIN)
	for mesh: MeshInstance3D in sample.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		if mesh.mesh.get_meta("nest_source_library", "") == COURTYARD_COVER and _bind_courtyard_cover(mesh, sky_origin):
			continue
		for surface in range(mesh.mesh.get_surface_count()):
			var original := mesh.get_active_material(surface)
			if original == null:
				continue
			var group := ESTATE_LIGHTING.lighting_group(mesh)
			var original_identity := "%d:%s"%[original.get_instance_id(),group]
			var share_opaque: bool = original is ShaderMaterial and original.shader != null and original.shader.resource_path in ["res://nest/rendering/estate_opaque.gdshader", "res://nest/furniture/shared/bedroom/m01_sheen.gdshader"] and original.next_pass == null
			if share_opaque:
				# Imported placements may own separate resources with identical
				# shader inputs, including the original fabric sheen. Keep room
				# ownership while sharing their GPU state; never replace the shader.
				var id := original.get_instance_id()
				if not opaque_inputs.has(id):
					var inputs: Array = [original.shader,original.resource_name,original.render_priority]
					for property: Dictionary in original.get_property_list():
						if str(property.name).begins_with("shader_parameter/") and property.usage & PROPERTY_USAGE_STORAGE:
							inputs.append([property.name,original.get(property.name)])
					opaque_inputs[id] = var_to_bytes(inputs)
				var key := var_to_bytes([group,opaque_inputs[id]])
				if not opaque_sources.has(key): opaque_sources[key] = original
				original = opaque_sources[key]
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
			ESTATE_LIGHTING.set_material(mesh, surface, owned[identity])
			if share_opaque:
				_opaque_bindings.append({"mesh":mesh,"surface":surface,"identity":original_identity,"shared":owned[identity]})
	# Restored instance batches own shared runtime materials, separate from the
	# hidden MeshInstance prototypes. Their daylight must follow the same switch.
	for batch: MultiMeshInstance3D in sample.find_children("*", "MultiMeshInstance3D", true, false):
		if batch.multimesh == null or batch.multimesh.mesh == null: continue
		for surface in range(batch.multimesh.mesh.get_surface_count()):
			var material := batch.material_override if batch.material_override != null else batch.multimesh.mesh.surface_get_material(surface)
			if material is ShaderMaterial:
				bind_natural_material(material)
	return counts


func set_opaque_shared(enabled: bool) -> void:
	# Reversible comparison keeps the exact original resource grouping and values.
	for binding: Dictionary in _opaque_bindings:
		var mesh := binding.mesh as MeshInstance3D
		if not is_instance_valid(mesh) or mesh.mesh == null or binding.surface >= mesh.mesh.get_surface_count(): continue
		RENDER_BATCHES.restore_before_write(mesh)
		var material: Material = binding.shared
		if not enabled:
			if not _unshared_opaque.has(binding.identity):
				var independent := material.duplicate() as ShaderMaterial
				_unshared_opaque[binding.identity] = independent
				_natural_materials.append(independent)
			material = _unshared_opaque[binding.identity]
		ESTATE_LIGHTING.set_material(mesh,binding.surface,material)


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
