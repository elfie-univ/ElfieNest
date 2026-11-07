extends Node3D
## Formal static asset review. Scene changes never reach live Nest authority.

const BASE := "res://v044-review/"
const DIRECTIONS := Vector3(1.0, 0.65, 1.2)
var ids: Array
var previews: Dictionary = {}
var current: Node3D
var camera: Camera3D
var light: DirectionalLight3D
var ambient: WorldEnvironment
var target: Vector3
var distance := 4.0
var yaw := 0.0
var pitch := 0.3
var active := ""
var active_focus: Array = []
var estate_overview := false
var auditing := false
var inspect_material := StandardMaterial3D.new()
var inspect_furniture_material := StandardMaterial3D.new()
var original_overlays := {}
var original_overrides := {}
var original_visibility := {}
var inspected_paths: Array = []
var inspecting_solo := false

func _ready() -> void:
	ids = JSON.parse_string(FileAccess.get_file_as_string(BASE + "menu.json"))
	if FileAccess.file_exists(BASE + "asset-previews.json"):
		previews = JSON.parse_string(FileAccess.get_file_as_string(BASE + "asset-previews.json"))
	camera = Camera3D.new()
	camera.near = 0.015
	camera.far = 1500
	add_child(camera)
	camera.make_current()
	light = DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-52, -28, 0)
	light.light_energy = 1.25
	add_child(light)
	ambient = WorldEnvironment.new()
	ambient.environment = Environment.new()
	ambient.environment.background_mode = Environment.BG_COLOR
	ambient.environment.background_color = Color("b6c4cb")
	ambient.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	ambient.environment.ambient_light_color = Color("f4f4fa")
	ambient.environment.ambient_light_energy = 0.7
	inspect_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	inspect_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	inspect_material.albedo_color = Color(0.10, 0.90, 0.64, 0.62)
	inspect_furniture_material.albedo_color = Color(0.13, 0.78, 0.53)
	inspect_furniture_material.roughness = 0.86
	add_child(ambient)
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.v044Review=[];addEventListener('message',e=>{if(e.source===parent&&e.origin===location.origin&&e.data?.channel==='nest-v044-review')window.v044Review.push(e.data)});")
	publish("ready", {"total": ids.size()})

func publish(kind: String, data: Dictionary = {}) -> void:
	data.merge({"channel": "nest-v044-review", "kind": kind}, true)
	if OS.has_feature("web"):
		JavaScriptBridge.eval("parent.postMessage(" + JSON.stringify(data) + ",location.origin)")

func _exit_tree() -> void:
	if is_instance_valid(ambient) and ambient.get_parent() == null:
		ambient.free()

func show_scene(id: String, preserve_camera: bool = false, focus_paths: Array = [], overview := false) -> int:
	if id == active and focus_paths == active_focus and overview == estate_overview and is_instance_valid(current): return visible_geometry()
	var preview: Dictionary = previews.get(id, {})
	var base_id := str(preview.get("base", id))
	var world := base_id == "reassembled"
	var full := world and focus_paths.is_empty()
	if preview.is_empty() and id not in ids: return -1
	var path := str(preview.get("path", "models/" + id + ".scn"))
	if not path.begins_with("res://"): path = BASE + path
	var scene := ResourceLoader.load(path, "PackedScene") as PackedScene
	if scene == null: return -1
	clear_inspection()
	if is_instance_valid(current): current.free()
	if ambient.get_parent() == self: remove_child(ambient)
	current = scene.instantiate() as Node3D
	add_child(current)
	if preview.get("source", false) and not prepare_library(preview): return -1
	camera.make_current()
	var env := current.find_children("*", "WorldEnvironment", true, false)
	if not full and env.is_empty(): add_child(ambient)
	light.visible = not full and base_id != "environment"
	# Frame the garden itself in the isolated asset view. Keep the sky shell
	# in the environment asset and full-scene assembly preview.
	if base_id in ["courtyard-layout", "meadow-layout"]:
		for mesh: MeshInstance3D in current.find_children("*", "MeshInstance3D", true, false):
			var data: Dictionary = mesh.get_meta("extras", {})
			var source_name := str(mesh.get_meta("v044_path", mesh.name)).get_file()
			if data.get("elfienestSkySurface", false) or source_name.begins_with("Transparent large arch rise"):
				mesh.hide()
	# Prototypes and the source surfaces behind the evaluated light patches
	# are hidden in the world. Reveal them only when inspected on their own.
	if base_id in ["plant-library", "forest-library", "forest-path", "meadow-ground"]:
		for mesh: MeshInstance3D in current.find_children("*", "MeshInstance3D", true, false):
			if mesh.mesh != null: mesh.show()
	if not focus_paths.is_empty(): isolate_geometry(focus_paths)
	if full: freeze_water()
	active = id
	active_focus = focus_paths
	estate_overview = overview
	if not preserve_camera: reset()
	return visible_geometry()

func prepare_library(preview: Dictionary) -> bool:
	var parts := {}
	for mesh: MeshInstance3D in current.find_children("*", "MeshInstance3D", true, false):
		if not preload("res://nest/assembly/glb_placement.gd").restore_materials(mesh): return false
		var extras: Dictionary = mesh.get_meta("extras", {})
		var path := str(extras.get("v044_path", ""))
		if not path.is_empty():
			mesh.set_meta("v044_path", path)
			parts[path] = mesh
			if extras.has("review_visible"):
				mesh.visible = bool(extras.review_visible)
			if preview.get("vertex_colors", false):
				apply_vertex_colors(mesh)
	var groups: Array = preview.get("groups", [])
	if groups.is_empty(): return not parts.is_empty()
	var front: bool = preview.get("front_row", false)
	if front: current.set_meta("review_front_row", true)
	var rows: Array[Dictionary] = []
	var shown := {}
	for paths: Array in groups:
		var group := Node3D.new()
		current.add_child(group)
		for path: String in paths:
			var mesh: MeshInstance3D = parts.get(path)
			if mesh == null: return false
			mesh.reparent(group, true)
			shown[path] = true
		if front:
			var facing := (group.get_child(0) as Node3D).basis.z
			group.rotate_y(-atan2(facing.x, facing.z))
		var bounds: AABB
		for mesh: MeshInstance3D in group.get_children():
			var box := mesh.global_transform * mesh.get_aabb()
			bounds = box if mesh.get_index() == 0 else bounds.merge(box)
		rows.append({"node": group, "bounds": bounds})
	if front:
		rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.bounds.size.y < b.bounds.size.y)
	for path: String in parts:
		parts[path].visible = shown.has(path)
	var x := 0.0
	var z := 0.0
	var depth := 0.0
	for i: int in rows.size():
		var row := rows[i]
		var bounds: AABB = row.bounds
		if not front and i > 0 and i % 8 == 0:
			x = 0.0
			z += depth + 0.35
			depth = 0.0
		row.node.global_position += Vector3(x, 0.0, -bounds.size.z * 0.5 if front else z) - bounds.position
		x += bounds.size.x + (0.18 if front else maxf(0.15, bounds.size.x * 0.18))
		depth = maxf(depth, bounds.size.z)
	return true

func apply_vertex_colors(instance: MeshInstance3D) -> void:
	var mesh := instance.mesh as ArrayMesh
	if mesh == null: return
	for surface: int in mesh.get_surface_count():
		if not (mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR): continue
		var material := instance.get_active_material(surface) as BaseMaterial3D
		if material == null or material.vertex_color_use_as_albedo: continue
		var preview_material := material.duplicate() as BaseMaterial3D
		preview_material.vertex_color_use_as_albedo = true
		instance.set_surface_override_material(surface, preview_material)

func clear_inspection() -> void:
	for node: GeometryInstance3D in original_overlays:
		node.material_overlay = original_overlays[node]
	for node: GeometryInstance3D in original_overrides:
		node.material_override = original_overrides[node]
	for node: GeometryInstance3D in original_visibility:
		node.visible = original_visibility[node]
	original_overlays.clear()
	original_overrides.clear()
	original_visibility.clear()
	inspected_paths = []
	inspecting_solo = false

func inspect_parts(paths: Array, solo: bool) -> int:
	var was_solo := inspecting_solo
	clear_inspection()
	if not is_instance_valid(current): return 0
	var selected := {}
	var wanted := {}
	for path: String in paths:
		wanted[path] = true
		var root_node := current.get_node_or_null(NodePath(path))
		if root_node == null: continue
		if root_node is GeometryInstance3D: selected[root_node] = true
		for mesh: GeometryInstance3D in root_node.find_children("*", "GeometryInstance3D", true, false):
			selected[mesh] = true
	var geometry := current.find_children("*", "GeometryInstance3D", true, false)
	var matched := {}
	for mesh: GeometryInstance3D in geometry:
		if selected.has(mesh) or wanted.has(mesh.get_meta("v044_path", "")):
			if mesh.is_visible_in_tree() and mesh.layers != 0:
				if mesh is MeshInstance3D and mesh.mesh == null: continue
				if mesh is MultiMeshInstance3D and mesh.multimesh == null: continue
				matched[mesh] = true
	if not matched.is_empty():
		if solo:
			for mesh: GeometryInstance3D in geometry:
				if mesh.visible and not matched.has(mesh):
					original_visibility[mesh] = true
					mesh.hide()
		else:
			var furniture: bool = previews.get(active, {}).get("furniture", false)
			for mesh: GeometryInstance3D in matched:
				if furniture:
					# Replace every surface while selected. A blended overlay can be
					# depth-occluded by parts of the same upholstered mesh.
					original_overrides[mesh] = mesh.material_override
					mesh.material_override = inspect_furniture_material
				else:
					original_overlays[mesh] = mesh.material_overlay
					mesh.material_overlay = inspect_material
		inspected_paths = paths
		inspecting_solo = solo
	if was_solo or inspecting_solo: reset()
	return matched.size()

func isolate_geometry(paths: Array) -> void:
	var keep := {}
	var ancestors := {}
	var wanted := {}
	var geometry := current.find_children("*", "GeometryInstance3D", true, false)
	var parts: Array[Node3D] = []
	for path: String in paths:
		wanted[path] = true
		var part := current.get_node_or_null(NodePath(path)) as Node3D
		if part != null and current.is_ancestor_of(part): parts.append(part)
	for mesh: GeometryInstance3D in geometry:
		if wanted.has(mesh.get_meta("v044_path", "")): parts.append(mesh)
	for part: Node3D in parts:
		if part is GeometryInstance3D: keep[part] = true
		for mesh: GeometryInstance3D in part.find_children("*", "GeometryInstance3D", true, false):
			keep[mesh] = true
		var ancestor := part.get_parent() as Node3D
		while ancestor != null and ancestor != current:
			ancestors[ancestor] = true
			ancestor.show()
			ancestor = ancestor.get_parent() as Node3D
	for mesh: GeometryInstance3D in geometry:
		mesh.visible = keep.has(mesh) or ancestors.has(mesh)
		if ancestors.has(mesh) and not keep.has(mesh): mesh.layers = 0

func freeze_water() -> void:
	# The stored scene retains the emitter and water shaders. The static A/B
	# evaluates both worlds with no random mist and the same water phase.
	for mist: CPUParticles3D in current.find_children("*", "CPUParticles3D", true, false):
		mist.emitting = false
		mist.hide()
	var seen := {}
	for mesh: MeshInstance3D in current.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		for index: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(index) as ShaderMaterial
			if material == null or seen.has(material): continue
			seen[material] = true
			# The receiving sheet never gets sampled by the live water controller;
			# an unset parameter still uses its shader's TIME fallback.
			var shader_name := material.shader.resource_path.get_file() if material.shader != null else ""
			if shader_name in ["estate_water.gdshader", "estate_shallow_water.gdshader", "estate_water_flow.gdshader"]:
				material.set_shader_parameter("presentation_time", 0.0)

func visible_geometry() -> int:
	var count := 0
	for item: GeometryInstance3D in current.find_children("*", "GeometryInstance3D", true, false):
		if not item.is_visible_in_tree(): continue
		if not active_focus.is_empty() and item.layers == 0: continue
		if item is MeshInstance3D and item.mesh == null: continue
		if item is MultiMeshInstance3D and item.multimesh == null: continue
		count += 1
	return count

func reset() -> void:
	if not is_instance_valid(current): return
	if estate_overview:
		set_camera(Vector3(0, 2, 6), Vector3(0, 46, 17), 101.0)
		return
	var found := false
	var bounds := AABB()
	for item: GeometryInstance3D in current.find_children("*", "GeometryInstance3D", true, false):
		if not item.is_visible_in_tree(): continue
		if not active_focus.is_empty() and item.layers == 0: continue
		if item is MeshInstance3D and item.mesh == null: continue
		var box := item.get_aabb()
		if item is MeshInstance3D and item.mesh is ArrayMesh and item.mesh.custom_aabb.has_volume():
			box = item.mesh.custom_aabb
		if not box.has_surface(): continue
		box = item.global_transform * box
		bounds = bounds.merge(box) if found else box
		found = true
	var focus := bounds.get_center()
	var size := maxf(bounds.size.length(), 0.3)
	if current.has_meta("review_front_row"):
		var viewport_size := get_viewport().get_visible_rect().size
		var aspect := clampf(viewport_size.x / maxf(viewport_size.y, 1.0), 0.1, 1.0)
		var front := Vector3(0, 0.18, 1).normalized()
		set_camera(focus, focus + front * size * 1.34 / aspect, 46.0)
		return
	set_camera(focus, focus + DIRECTIONS.normalized() * size * 1.34, 46.0)

func set_camera(focus: Vector3, position: Vector3, fov: float) -> void:
	target = focus
	var offset := position - focus
	distance = offset.length()
	yaw = atan2(offset.x, offset.z)
	pitch = asin(offset.y / distance)
	camera.fov = fov
	update_camera()

func update_camera() -> void:
	camera.position = target + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	camera.look_at(target, Vector3.UP)
	camera.make_current()

func _unhandled_input(event: InputEvent) -> void:
	if auditing or current == null: return
	if event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_MASK_LEFT:
		yaw -= event.relative.x * 0.006
		pitch = clampf(pitch + event.relative.y * 0.006, -1.4, 1.4)
		update_camera()
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP: distance = maxf(0.04, distance * 0.9)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN: distance = minf(800.0, distance / 0.9)
		else: return
		update_camera()

func _process(_delta: float) -> void:
	if not OS.has_feature("web"): return
	var messages: Variant = JSON.parse_string(str(JavaScriptBridge.eval("JSON.stringify(window.v044Review.splice(0))")))
	if not messages is Array: return
	for msg: Dictionary in messages:
		if msg.get("type") == "hello": publish("ready", {"total": ids.size()})
		elif auditing: continue
		elif msg.get("type") == "show":
			var next := str(msg.get("id"))
			var selection := str(msg.get("selection", next))
			var focus_paths: Array = msg.get("focus", [])
			var overview: bool = selection == "view:estate-layout"
			var count := show_scene(next, false, focus_paths, overview)
			if count > 0: inspect_parts(msg.get("inspect", []), msg.get("solo", false))
			publish("shown" if count > 0 else "error", {"id": selection, "geometry": count})
		elif msg.get("type") == "reset": reset()
		elif msg.get("type") == "audit": audit()

func rendered_image() -> Image:
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	return get_viewport().get_texture().get_image()

func audit() -> void:
	auditing = true
	var restore := active
	var restore_focus := active_focus
	var restore_overview := estate_overview
	var restore_inspection := inspected_paths
	var restore_solo := inspecting_solo
	clear_inspection()
	var assets := {}
	var failures := []
	for id: String in ids:
		var preview: Dictionary = previews.get(id, {})
		var geometry := show_scene(id, false, preview.get("focus", []), id == "view:estate-layout")
		var image := await rendered_image()
		var colors := {}
		if image != null and not image.is_empty():
			var thumb := image.duplicate() as Image
			thumb.resize(64, 64, Image.INTERPOLATE_NEAREST)
			for x: int in 64:
				for y: int in 64: colors[thumb.get_pixel(x, y).to_rgba32()] = true
		if geometry <= 0 or colors.size() <= 1: failures.append(id)
		assets[id] = {"geometry": geometry, "sample_colors": colors.size()}
		publish("progress", {"done": assets.size(), "total": ids.size()})
	show_scene(restore, false, restore_focus, restore_overview)
	reset()
	inspect_parts(restore_inspection, restore_solo)
	auditing = false
	publish("audit", {"assets": assets, "failures": failures})
