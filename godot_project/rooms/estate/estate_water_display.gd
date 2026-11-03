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
var _wave_materials: Array[ShaderMaterial] = []
var spillway_materials: Array[ShaderMaterial] = []
var spillway_rings: Array[Dictionary] = []
var _spillway_edges: Array[StandardMaterial3D] = []
var _waterfall_material: ShaderMaterial
var night_enabled := false
var _manage_environment := true
var _seconds := 0.0
@export_enum("auto", "random", "fixed") var fountain_programme := "auto"
@export var fountain_seed := 20261102
var fountain_show: Node3D
var _visibility_timer: Timer
var _on_screen := false
var _paused := false
var _epoch_msec := 0
var _paused_msec := 0
var _component_holds: Dictionary = {}
var _component_offsets := {"fountain": 0.0, "lake": 0.0}

func component_time(component: String, seconds: float) -> float:
	return float(_component_holds[component]) if _component_holds.has(component) else seconds - float(_component_offsets[component])

func set_component_paused(component: String, paused: bool) -> bool:
	if not _component_offsets.has(component): return false
	var now := presentation_seconds()
	if paused and not _component_holds.has(component): _component_holds[component] = component_time(component, now)
	elif not paused and _component_holds.has(component):
		_component_offsets[component] = now - float(_component_holds[component])
		_component_holds.erase(component)
	return true

func component_paused(component: String) -> bool:
	return _component_holds.has(component)

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
	var channel := geometry.find_child("COMPLETE Short east spillway", true, false) as MeshInstance3D
	var channel_bounds := channel.global_transform * channel.get_aabb()
	for water: MeshInstance3D in [pool, channel]:
		var material := water.get_active_material(0) as ShaderMaterial
		material.set_shader_parameter("fountain_waves", true)
		material.set_shader_parameter("fountain_center", pool_bounds.get_center())
		material.set_shader_parameter("pool_radius", pool_bounds.size.x * 0.5)
		material.set_shader_parameter("channel_end_radius", channel_bounds.end.x-pool_bounds.get_center().x)
		_wave_materials.append(material)
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		var center := (mesh.global_transform * mesh.get_aabb()).get_center()
		var outside_pool := center.x < pool_bounds.position.x or center.x > pool_bounds.end.x or center.z < pool_bounds.position.z or center.z > pool_bounds.end.z
		for surface in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material == null: continue
			var role := str(material.get_meta("estate_water_role", ""))
			# Use the channel's role: its curved inlet meets the pool bounds.
			if role == "spillway" or (outside_pool and role in ["jet", "foam"]): spillway_materials.append(material)
			if outside_pool and role == "ripple":
				var bounds := mesh.global_transform * mesh.get_aabb()
				spillway_rings.append({"material": material, "radius": maxf(bounds.size.x, bounds.size.z) * 0.5})
		if outside_pool: continue
		for surface in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material != null and material.get_meta("estate_water_role", "") in ["surface", "jet", "ripple"]:
				fountain_materials.append(material)
				if material.get_meta("estate_water_role", "") == "ripple":
					# The water surface now carries moving fronts all the way to the wall.
					mesh.visible = false
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
	spillway_rings.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return float(a["radius"])<float(b["radius"]))
	_bind_spillway_lights(geometry, pool)
	fountain_show = preload("res://rooms/estate/fountain_show.gd").new()
	fountain_show.name = "RhythmicFountain"
	add_child(fountain_show)
	fountain_show.bind(geometry,pool,fountain_materials,float(fountain_rings[-1].radius))
	if OS.has_feature("web"):
		var choice:Variant=JavaScriptBridge.eval("new URLSearchParams(window.parent.location.search).get('fountain')")
		if choice is String and choice in ["auto","fixed","random"]: fountain_programme=choice
		var seed_text:Variant=JavaScriptBridge.eval("new URLSearchParams(window.parent.location.search).get('fountain_seed')")
		if seed_text is String and seed_text.is_valid_int(): fountain_seed=clampi(int(seed_text),0,2147483647)
	fountain_show.programme=fountain_programme
	fountain_show.random_programme=fountain_programme=="random"
	fountain_show.programme_seed=fountain_seed
	_epoch_msec = Time.get_ticks_msec()
	_visibility_timer = Timer.new()
	_visibility_timer.wait_time = 0.25
	_visibility_timer.timeout.connect(refresh_visibility)
	add_child(_visibility_timer)
	_visibility_timer.start()
	sample(0.0, false)
	refresh_visibility()

func _bind_spillway_lights(geometry: Node3D, pool: MeshInstance3D) -> void:
	var coping := geometry.find_child("ROAD REF • fountain radial limestone coping", true, false) as MeshInstance3D
	var rim_y := (coping.global_transform * coping.get_aabb()).end.y + 0.008
	var waterfall := geometry.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
	assert(waterfall != null, "The area effect requires the authored water curtain")
	_waterfall_material = waterfall.get_active_material(0) as ShaderMaterial
	_waterfall_material.set_shader_parameter("is_waterfall", true)
	_waterfall_material.set_shader_parameter("waterfall_min", waterfall.get_aabb().position)
	_waterfall_material.set_shader_parameter("waterfall_size", waterfall.get_aabb().size)
	var outline := preload("res://rooms/estate/estate_shore_finish.gd").ribbon_path(geometry)
	for side: String in ["north", "south"]:
		var wall := geometry.find_child("CY R001 spillway %s continuous side wall" % side, true, false) as MeshInstance3D
		assert(wall != null, "The spillway edge light requires its authored stone wall")
		var bounds := wall.global_transform * wall.get_aabb()
		var material := StandardMaterial3D.new()
		material.resource_name = "Outdoor spillway concealed warm edge lamp"
		material.albedo_color = Color(0.68, 0.57, 0.38)
		material.emission_enabled = true
		material.emission = Color(1.0, 0.77, 0.44)
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		var z := bounds.end.z - 0.05 if side == "north" else bounds.position.z + 0.05
		var center := (pool.global_transform * pool.get_aabb()).get_center()
		var radius := INF
		for vertex: Vector3 in coping.mesh.get_faces():
			var point := coping.global_transform * vertex
			radius = minf(radius, Vector2(point.x - center.x, point.z - center.z).length())
		radius += 0.05
		var ring_x := center.x + sqrt(radius * radius - (z - center.z) * (z - center.z))
		var shore_join := outline[0] if absf(outline[0].z - z) < absf(outline[-1].z - z) else outline[-1]
		assert(absf(shore_join.z - z) < 0.001, "The guide must meet the open ribbon endpoint at its real channel side")
		var route := PackedVector3Array([
			Vector3(ring_x, rim_y, z),
			Vector3(bounds.end.x, rim_y, z),
			Vector3(bounds.end.x, shore_join.y, z),
			shore_join,
		])
		var vertices := PackedVector3Array()
		var normals := PackedVector3Array()
		var indices := PackedInt32Array()
		for route_index in range(route.size()):
			var point := route[route_index]
			# A shared miter joins the descent to the sideways bank return.
			var tangent := route[mini(route_index + 1, route.size() - 1)] - route[maxi(route_index - 1, 0)]
			var across := Vector3(-tangent.z, 0, tangent.x).normalized() * 0.05
			if across.is_zero_approx(): across = Vector3(0, 0, 0.05)
			vertices.append_array(PackedVector3Array([point - across, point + across]))
			normals.append_array(PackedVector3Array([Vector3.UP, Vector3.UP]))
		for segment in range(route.size() - 1):
			var start := segment * 2
			indices.append_array(PackedInt32Array([start, start + 1, start + 3, start, start + 3, start + 2]))
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		arrays[Mesh.ARRAY_NORMAL] = normals
		arrays[Mesh.ARRAY_INDEX] = indices
		var ribbon := ArrayMesh.new()
		ribbon.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		ribbon.surface_set_material(0, material)
		var edge := MeshInstance3D.new()
		edge.name = "SpillwayEdge_" + side
		edge.mesh = ribbon
		edge.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(edge)
		edge.global_transform = Transform3D.IDENTITY
		edge.set_meta("light_route", route)
		_spillway_edges.append(material)

func sample(seconds: float, night: bool) -> void:
	var fountain_seconds := component_time("fountain", seconds)
	var lake_seconds := component_time("lake", seconds)
	var phase := fposmod(seconds, 24.0) / 8.0
	var index := int(phase)
	var color: Color = COLORS[index].lerp(COLORS[(index + 1) % COLORS.size()], smoothstep(0.0, 1.0, phase - index))
	# A subdued accent on the existing lake surface, without added beams or stripes.
	var lake_material := lake.get_active_material(0) as ShaderMaterial
	lake_material.set_shader_parameter("presentation_time", lake_seconds)
	lake_material.set_shader_parameter("show_time", lake_seconds)
	lake_material.set_shader_parameter("accent_color",Vector3(color.r,color.g,color.b))
	lake_material.set_shader_parameter("accent_strength",0.15 if night else 0.0)
	# Light only the original fountain water, never a free-standing beam.
	for material: ShaderMaterial in fountain_materials:
		material.set_shader_parameter("presentation_time", fountain_seconds)
		material.set_shader_parameter("accent_color", Vector3(color.r, color.g, color.b))
		var strength := 0.35
		material.set_shader_parameter("accent_strength", strength if night else 0.0)
	# Each actual pool ring peaks later than the smaller one, then fades.
	var cycle := fposmod(fountain_seconds,5.0)
	for ring_index in range(fountain_rings.size()):
		var material := fountain_rings[ring_index]["material"] as ShaderMaterial
		var distance := (cycle-(0.55+float(ring_index)*0.7))/0.33
		var pulse := exp(-distance*distance)
		material.set_shader_parameter("accent_strength",0.04+1.8*pulse if night else 0.0)
	var lead: Dictionary = fountain_show.sample(fountain_seconds,night)
	for material: ShaderMaterial in _wave_materials:
		var time := lake_seconds if material == lake_material else fountain_seconds
		material.set_shader_parameter("show_time", time)
		material.set_shader_parameter("presentation_time", time)
		material.set_shader_parameter("show_night", 1.0 if night else 0.0)
		material.set_shader_parameter("flower_height", lead.flower_height)
		material.set_shader_parameter("flower_reach", lead.flower_reach)
		material.set_shader_parameter("flower_colors", lead.flower_colors)
		material.set_shader_parameter("impacts", lead.impacts)
		material.set_shader_parameter("impact_colors", lead.impact_colors)
	_lamp.visible = night and _on_screen and not _paused
	_lamp.light_color = lead.light_color
	_lamp.light_energy = 0.45 * maxf(float(lead.energy),float(lead.flower_energy)) if night else 0.0
	# Two quiet warm guides frame the channel; cool highlights stay on the
	# original moving water and impact rings, rather than adding a light beam.
	for material: StandardMaterial3D in _spillway_edges:
		material.emission_energy_multiplier = 1.1 if night else 0.0
	for material: ShaderMaterial in spillway_materials:
		material.set_shader_parameter("presentation_time", fountain_seconds)
		var role := str(material.get_meta("estate_water_role"))
		var strength := 0.5 if role == "jet" else (0.22 if role == "foam" else 0.32)
		material.set_shader_parameter("accent_color", Vector3(0.35, 0.68, 0.78))
		material.set_shader_parameter("accent_strength", strength if night else 0.0)
	var landing_cycle := fposmod(seconds, 3.0)
	for landing_index in range(spillway_rings.size()):
		var material := spillway_rings[landing_index]["material"] as ShaderMaterial
		var distance := (landing_cycle - (0.2 + float(landing_index) * 0.35)) / 0.28
		material.set_shader_parameter("accent_color", Vector3(0.35, 0.68, 0.78))
		material.set_shader_parameter("accent_strength", 0.03 + 0.22 * exp(-distance * distance) if night else 0.0)
	_waterfall_material.set_shader_parameter("waterfall_glow", 1.0 if night else 0.0)
	_waterfall_material.set_shader_parameter("waterfall_phase", seconds)
	if not _manage_environment: return
	for binding: Dictionary in _day_lights:
		(binding["light"] as DirectionalLight3D).light_energy = float(binding["energy"]) * (0.045 if night else 1.0)
	for binding: Dictionary in _sky:
		(binding["mesh"] as MeshInstance3D).visible = bool(binding["visible"]) and not night
	_environment.background_color = Color(0.015, 0.025, 0.05) if night else _day_environment["background_color"]
	_environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	_environment.ambient_light_energy = 0.0
	_environment.background_energy_multiplier = 0.2 if night else float(_day_environment["background_energy_multiplier"])


func set_night(value: bool) -> void:
	night_enabled = value
	sample(presentation_seconds(), night_enabled)


func presentation_seconds() -> float:
	var now := _paused_msec if _paused else Time.get_ticks_msec()
	return float(now - _epoch_msec) / 1000.0


func set_presentation_paused(paused: bool) -> void:
	if paused != _paused:
		if paused: _paused_msec = Time.get_ticks_msec()
		else: _epoch_msec += Time.get_ticks_msec() - _paused_msec
	_paused = paused
	if _visibility_timer != null: _visibility_timer.paused = paused
	refresh_visibility()


func refresh_visibility() -> void:
	var camera := get_viewport().get_camera_3d()
	_on_screen = not _paused and is_visible_in_tree() and camera != null and fountain_show.visible_from(camera)
	var nearby := camera != null and camera.global_position.distance_to(fountain_show.global_position)<30.0
	fountain_show.set_detail(_on_screen,nearby)
	_lamp.visible = night_enabled and _on_screen
	set_process(not _manage_environment and _on_screen)


func _process(_delta: float) -> void:
	if not _on_screen or _paused: return
	_seconds = presentation_seconds()
	sample(_seconds, night_enabled)
