extends Node3D
## Explicit browser-only experiment. It never constructs the semantic/physics world.

const SOURCE := "res://rooms/estate/ElfieNest-complete-final.glb"
const SURFACE := preload("res://rooms/estate/estate_surface.gd")
const SHEEN := preload("res://runtime/lab/m01_sheen.gdshader")
const LIGHTING_SAMPLE := preload("res://rooms/estate/estate_lighting_sample.gd")
const MIRROR_X := Transform3D(Basis.FLIP_X, Vector3.ZERO)
var camera_owner: Node3D
var camera: Camera3D
var source_colors: Dictionary = {}
var counts := {"meshes": 0, "triangles": 0, "clearcoat": 0, "sheen": 0, "glass": 0}
var _geometry: Node3D
var _floor_frame := Transform3D.IDENTITY
var _elapsed := 0.0
var _mesh_cache: Dictionary = {}
var _material_cache: Dictionary = {}
var _mirror_cache: Dictionary = {}
var _window_cache: Dictionary = {}
var _lighting_sample_report: Dictionary = {}


static func isolate_host(host: Node) -> void:
	# Hidden preview geometry does not isolate lights or WorldEnvironment nodes.
	# Apply only before attaching this explicitly requested experiment.
	for existing: Node in host.find_children("*", "WorldEnvironment", true, false):
		(existing as WorldEnvironment).environment = null
	for existing: Node in host.find_children("*", "Light3D", true, false):
		(existing as Light3D).visible = false


static func is_requested(mode: String = "m01_sample") -> bool:
	if not OS.has_feature("web"):
		return false
	# Use the same string boundary as the existing main.gd Lab mode selector.
	var query: Variant = JavaScriptBridge.eval("window.location.search")
	if not query is String:
		return false
	for part in String(query).trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2 and pair[0] == "mode":
			return String(pair[1]).uri_decode() == mode
	return false


func _ready() -> void:
	build()


func build() -> void:
	print("M01_OPTICAL_SAMPLE_BUILD_START")
	_geometry = Node3D.new()
	_geometry.name = "M01UnmodifiedGeometry"
	add_child(_geometry)
	var source_root := (load(SOURCE) as PackedScene).instantiate() as Node3D
	source_root.visible = false
	add_child(source_root)
	for node: Node in source_root.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if extras.get("module", "") != "M01":
			continue
		if str(extras.get("source_name", "")).contains("continuous lower floor"):
			_floor_frame = mesh.global_transform
		mesh.reparent(_geometry, true)
		mesh.visible = true
		mesh.layers = 3 if bool(extras.get("furniture", false)) else 1
		mesh.mesh = _full_detail(mesh.mesh)
		SURFACE.repair_window_normals(mesh, _window_cache)
		counts["meshes"] += 1
		var cloth := false
		for surface in range(mesh.mesh.get_surface_count()):
			var original := mesh.get_active_material(surface) as BaseMaterial3D
			if original == null:
				continue
			source_colors[original.resource_name] = original.albedo_color
			var calibrated := _optics(original, bool(extras.get("glass", false)))
			mesh.set_surface_override_material(surface, calibrated)
			# Both custom physical surfaces supply their own hemisphere irradiance.
			cloth = cloth or calibrated is ShaderMaterial
			counts["triangles"] += mesh.mesh.surface_get_array_index_len(surface) / 3
			if bool(extras.get("glass", false)):
				mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			if bool(extras.get("lighting_diffuser", false)) and calibrated is BaseMaterial3D:
				(calibrated as BaseMaterial3D).emission_energy_multiplier = 0.15
		if not cloth:
			mesh.layers |= 4
		_restore_fixture_lights(mesh, extras)
	source_root.free()
	for node: Node in _geometry.get_children():
		var mesh := node as MeshInstance3D
		if mesh.global_basis.determinant() < 0.0:
			mesh.set_meta("m01_source_mesh", mesh.mesh)
			mesh.set_meta("m01_source_frame", mesh.global_transform)
			mesh.mesh = _normalize_mirror(mesh.mesh as ArrayMesh)
			mesh.global_transform = mesh.global_transform * MIRROR_X
	_build_lighting()
	camera = Camera3D.new()
	camera.name = "M01ReferenceCamera"
	camera.fov = 42.0
	camera.near = 0.05
	camera.far = 500.0
	add_child(camera)
	set_camera(_floor_frame * Vector3(0, 1.55, 2.2), _floor_frame * Vector3(0, 1.0, -0.4))
	if DisplayServer.get_name() != "headless":
		get_viewport().msaa_3d = Viewport.MSAA_4X
	if OS.has_feature("web"):
		var pose: Variant = JSON.parse_string(str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('opticsOrbit')||'null'")))
		if pose is Dictionary and pose.get("position") is Array and pose.get("target") is Array:
			set_camera(_vector(pose["position"]), _vector(pose["target"]))
		JavaScriptBridge.eval("window.__m01SampleQueue=[];window.addEventListener('message',e=>{if(e.origin===location.origin&&e.data?.channel==='m01-optical-sample'&&e.data.type==='camera')window.__m01SampleQueue.push(e.data);});")
		_apply_requested_lighting_sample()
		_publish()
	print("M01_OPTICAL_SAMPLE ", JSON.stringify(counts))


func _full_detail(source: Mesh) -> Mesh:
	var identity := source.get_instance_id()
	if _mesh_cache.has(identity):
		return _mesh_cache[identity]
	if not source is ArrayMesh:
		return source
	var surfaces: Array = source.get("_surfaces").duplicate(true)
	for surface: Dictionary in surfaces:
		surface["lods"] = []
	var result := ArrayMesh.new()
	result.set("_surfaces", surfaces)
	result.custom_aabb = (source as ArrayMesh).custom_aabb
	_mesh_cache[identity] = result
	return result


func _normalize_mirror(source: ArrayMesh) -> ArrayMesh:
	var identity := source.get_instance_id()
	if _mirror_cache.has(identity):
		return _mirror_cache[identity]
	# GLES3 does not flip glFrontFace for mirrored double-sided instances.
	# Apply the reflection to local geometry and reverse winding instead.
	# The positive instance frame then produces the same world-space surface.
	var result := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface)
		var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
		for index in range(vertices.size()):
			vertices[index] = Basis.FLIP_X * vertices[index]
		arrays[Mesh.ARRAY_VERTEX] = vertices
		var normals := arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array
		for index in range(normals.size()):
			normals[index] = Basis.FLIP_X * normals[index]
		arrays[Mesh.ARRAY_NORMAL] = normals
		if arrays[Mesh.ARRAY_TANGENT] is PackedFloat32Array:
			var tangents := arrays[Mesh.ARRAY_TANGENT] as PackedFloat32Array
			for index in range(0, tangents.size(), 4):
				tangents[index] = -tangents[index]
				tangents[index + 3] = -tangents[index + 3]
			arrays[Mesh.ARRAY_TANGENT] = tangents
		var indices := arrays[Mesh.ARRAY_INDEX] as PackedInt32Array
		for index in range(0, indices.size(), 3):
			var second := indices[index + 1]
			indices[index + 1] = indices[index + 2]
			indices[index + 2] = second
		arrays[Mesh.ARRAY_INDEX] = indices
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays)
		result.surface_set_material(surface, source.surface_get_material(surface))
	result.custom_aabb = MIRROR_X * source.get_aabb()
	_mirror_cache[identity] = result
	return result


func _optics(original: BaseMaterial3D, glass: bool) -> Material:
	var identity := original.get_instance_id()
	if _material_cache.has(identity):
		return _material_cache[identity]
	var source := original
	var definition: Dictionary = source.get_meta("m01_reference_optics", {})
	var extensions: Dictionary = definition.get("extensions", {})
	var result: Material = original.duplicate()
	if extensions.has("KHR_materials_sheen"):
		var sheen: Dictionary = extensions["KHR_materials_sheen"]
		var fabric := ShaderMaterial.new()
		fabric.shader = SHEEN
		fabric.set_shader_parameter("source_albedo", original.albedo_color)
		fabric.set_shader_parameter("source_roughness", original.roughness)
		fabric.set_shader_parameter("source_normal", original.normal_texture)
		fabric.set_shader_parameter("source_normal_scale", original.normal_scale)
		fabric.set_shader_parameter("sheen_color", _vector(sheen.get("sheenColorFactor", [0, 0, 0])))
		fabric.set_shader_parameter("sheen_roughness", float(sheen.get("sheenRoughnessFactor", 0.8)))
		result = fabric
		counts["sheen"] += 1
	else:
		var physical := result as BaseMaterial3D
		physical.diffuse_mode = BaseMaterial3D.DIFFUSE_LAMBERT
		if extensions.has("KHR_materials_clearcoat"):
			var coat: Dictionary = extensions["KHR_materials_clearcoat"]
			physical.clearcoat_enabled = true
			physical.clearcoat = float(coat.get("clearcoatFactor", 0.0))
			# Three's GGX alpha is max(roughness, .0525)^2; GLES3's coat
			# instead maps this control to mix(.001, .1, value).
			var coat_roughness := maxf(float(coat.get("clearcoatRoughnessFactor", 0.0)), 0.0525)
			physical.clearcoat_roughness = clampf((coat_roughness * coat_roughness - 0.001) / 0.099, 0.0, 1.0)
			counts["clearcoat"] += 1
		if glass:
			physical.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			physical.albedo_color.a = 0.075
			physical.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
			physical.refraction_enabled = false
			physical.roughness = 0.18
			physical.metallic_specular = absf((1.12 - 1.0) / (1.12 + 1.0)) / 0.4
			counts["glass"] += 1
		if not glass and SURFACE.supports(physical):
			var coat: Dictionary = extensions.get("KHR_materials_clearcoat", {})
			result = SURFACE.make_material(physical, float(coat.get("clearcoatFactor", 0.0)), float(coat.get("clearcoatRoughnessFactor", 0.0)))
	_material_cache[identity] = result
	return result


func _build_lighting() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("dce6e0")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	var upper := Color.hex(0xd7ebffff).srgb_to_linear()
	var lower := Color.hex(0x5a685dff).srgb_to_linear()
	environment.ambient_light_color = lower.lerp(upper, 0.5).linear_to_srgb()
	environment.ambient_light_energy = 0.72 / PI
	# GLES3 applies background energy during sky generation and again during
	# sampling. Keep it neutral and put radiance units into the linear panorama.
	environment.background_energy_multiplier = 1.0
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.tonemap_exposure = 0.88
	environment.tonemap_white = 1.0
	var sky := Sky.new()
	var material := PanoramaSkyMaterial.new()
	var image := Image.create(512, 256, false, Image.FORMAT_RGB8)
	for y in range(image.get_height()):
		var weight := cos((float(y) + 0.5) / image.get_height() * PI) * 0.5 + 0.5
		var color := (lower.lerp(upper, weight) * (0.72 / PI)).linear_to_srgb()
		for x in range(image.get_width()):
			image.set_pixel(x, y, color)
	image.generate_mipmaps()
	material.panorama = ImageTexture.create_from_image(image)
	sky.sky_material = material
	environment.sky = sky
	world.environment = environment
	add_child(world)
	# Reproduce the reference's normal-dependent HemisphereLight without sky
	# convolution: mean + half-difference * normal.y. Cloth already provides
	# this irradiance in its shader, so these diffuse-only lights use layer 4.
	for up in [true, false]:
		var hemisphere := DirectionalLight3D.new()
		hemisphere.name = "ReferenceHemisphereUpper" if up else "ReferenceHemisphereLower"
		hemisphere.light_color = ((upper - lower) * 0.5).linear_to_srgb()
		hemisphere.light_energy = 0.72 / PI
		hemisphere.light_negative = not up
		hemisphere.light_specular = 0.0
		hemisphere.light_cull_mask = 4
		hemisphere.rotation_degrees.x = -90.0 if up else 90.0
		add_child(hemisphere)
	for entry: Array in [[0xffe7c3ff, 1.05, Vector3(-20, 35, 24)], [0xcdeaffff, 0.65, Vector3(22, 25, -24)], [0xffffffff, 0.30, Vector3(0, 15, 32)]]:
		var light := DirectionalLight3D.new()
		light.light_color = Color.hex(entry[0])
		light.light_energy = float(entry[1]) / PI
		light.shadow_enabled = entry[1] == 1.05
		if light.shadow_enabled:
			# Compatibility adds the shadowed light after separately tonemapping
			# it. Match the reference's displayed sun contrast, not its raw watts.
			light.light_energy *= 0.04
		light.directional_shadow_max_distance = 40.0
		light.shadow_bias = 0.03
		light.shadow_normal_bias = 0.1
		add_child(light)
		light.position = entry[2]
		light.look_at(Vector3.ZERO)
	# Selecting M01 in the reference hides geometry, not its shared light rig.
	for index in range(8):
		var angle := deg_to_rad(-40.0 + index * 260.0 / 7.0)
		_add_point("ReferenceRoomPoint", Color.hex(0xffc889ff), 3.0, 8.0, Vector3(13.55 * cos(angle), 1.75, -13.55 * sin(angle)))
	for height in [2.5, 5.8, 8.5]:
		_add_point("ReferenceCentralPoint", Color.hex(0xffd49dff), 12.0, 11.0, Vector3(0.0, height, 0.0))


func _add_point(label: String, color: Color, intensity: float, distance: float, position: Vector3) -> void:
	var light := OmniLight3D.new()
	light.name = label
	light.light_color = color
	light.light_energy = intensity / PI
	light.omni_range = distance
	light.omni_attenuation = 2.0
	light.shadow_enabled = false
	add_child(light)
	light.global_position = position


func _restore_fixture_lights(mesh: MeshInstance3D, extras: Dictionary) -> void:
	for source: Dictionary in extras.get("design_lights", []):
		var light := SpotLight3D.new()
		light.name = "M01AuthoredDayFixture"
		light.light_color = Color.hex((int(source.get("color", 0xffdfb5)) << 8) | 0xff)
		light.light_energy = float(source["intensity"]) * 0.08 / PI
		light.spot_range = float(source["distance"])
		light.spot_angle = rad_to_deg(float(source["angle"]))
		light.spot_angle_attenuation = 1.0
		add_child(light)
		light.global_position = mesh.global_transform * _vector(source["position"])
		var target := mesh.global_transform * _vector(source["target"])
		var up := Vector3.FORWARD if absf((target - light.global_position).normalized().dot(Vector3.UP)) > 0.99 else Vector3.UP
		light.look_at(target, up)


func set_camera(position: Vector3, target: Vector3) -> void:
	camera.global_position = position
	camera.look_at(target)
	camera.make_current()
	if camera_owner != null:
		camera_owner.call("configure_m01_optical_sample", camera, target)


func _process(delta: float) -> void:
	if not OS.has_feature("web"):
		return
	var batch: Variant = JavaScriptBridge.eval("JSON.stringify(window.__m01SampleQueue?.splice(0)||[])")
	var messages: Variant = JSON.parse_string(str(batch))
	if messages is Array:
		for message: Dictionary in messages:
			if message.get("position") is Array and message.get("target") is Array:
				set_camera(_vector(message["position"]), _vector(message["target"]))
	_elapsed += delta
	if _elapsed >= 1.0:
		_elapsed = 0.0
		_publish()


func _publish() -> void:
	var target: Vector3 = camera_owner.get("_camera_target") if camera_owner != null else camera.position - camera.basis.z
	var report := {"ready": true, "counts": counts, "position": [camera.global_position.x, camera.global_position.y, camera.global_position.z], "target": [target.x, target.y, target.z], "fov": camera.fov, "msaa": get_viewport().msaa_3d, "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME), "render_primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME), "fps": Engine.get_frames_per_second()}
	if not _lighting_sample_report.is_empty():
		report["lighting_sample"] = _lighting_sample_report
	var active_environment := get_world_3d().environment
	if active_environment != null:
		report["environment"] = {"ambient": active_environment.ambient_light_source, "ambient_energy": active_environment.ambient_light_energy, "sky_energy": active_environment.background_energy_multiplier, "reflection": active_environment.reflected_light_source}
	JavaScriptBridge.eval("window.__m01Sample=" + JSON.stringify(report) + ";document.documentElement.dataset.m01Sample=JSON.stringify(window.__m01Sample)")


static func _vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func _apply_requested_lighting_sample() -> void:
	if not is_requested():
		return
	var preset := str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('lighting')||''"))
	var levels := {"day": 1.0, "twilight": 0.45, "night": 0.0}
	if not levels.has(preset):
		return
	var control := LIGHTING_SAMPLE.new()
	var bindings := control.bind_m01(self)
	control.apply_sample(float(levels[preset]))
	_lighting_sample_report = {"preset": preset, "daylight": levels[preset], "bindings": bindings}
	print("M01_LIGHTING_SAMPLE ", JSON.stringify(_lighting_sample_report))
