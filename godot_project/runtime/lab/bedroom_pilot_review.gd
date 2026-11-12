extends Node3D
const RENDER_BATCHES := preload("res://nest/estate/estate_instance_batches.gd")

var camera: Camera3D
var target := Vector3.ZERO
var distance := 4.0
var yaw := 0.0
var pitch := 0.2
var original := false
var caption: Label
var _last_publish := -2000
var single_bed: Node3D
var single_light: DirectionalLight3D
var single_mode := false
var scene_button: Button
var asset_button: Button
var pressed_at := Vector2.ZERO
var selected_mesh: MeshInstance3D
var selection_material: StandardMaterial3D
var faces_cache := {}

func _ready() -> void:
	camera = $Snapshot/Camera3D
	camera.reparent(self)
	camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	camera.near = 0.03
	camera.far = 1000.0
	var layer := CanvasLayer.new()
	add_child(layer)
	caption = Label.new()
	caption.position = Vector2(12, 12)
	caption.add_theme_font_override("font", load("res://nest/ui/fonts/NotoSansSC-ObservationHUD.ttf"))
	caption.add_theme_font_size_override("font_size", 28)
	caption.add_theme_color_override("font_shadow_color", Color.BLACK)
	caption.add_theme_constant_override("shadow_outline_size", 4)
	layer.add_child(caption)
	caption.visible = false
	var tabs := HBoxContainer.new()
	tabs.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	tabs.position = Vector2(-500, 48)
	layer.add_child(tabs)
	tabs.visible = false
	scene_button = Button.new()
	scene_button.text = "整体场景"
	scene_button.add_theme_font_override("font", load("res://nest/ui/fonts/NotoSansSC-ObservationHUD.ttf"))
	scene_button.add_theme_font_size_override("font_size", 32)
	scene_button.pressed.connect(_show_scene)
	tabs.add_child(scene_button)
	asset_button = Button.new()
	asset_button.text = "单件资产：床"
	asset_button.add_theme_font_override("font", load("res://nest/ui/fonts/NotoSansSC-ObservationHUD.ttf"))
	asset_button.add_theme_font_size_override("font_size", 32)
	asset_button.pressed.connect(_show_bed)
	tabs.add_child(asset_button)
	single_bed = $Snapshot/BedroomFurnitureM01/bed_A.duplicate() as Node3D
	add_child(single_bed)
	single_bed.visible = false
	selection_material = StandardMaterial3D.new()
	selection_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	selection_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	selection_material.albedo_color = Color(0.13, 0.9, 0.55, 0.55)
	single_light = DirectionalLight3D.new()
	single_light.rotation_degrees = Vector3(-55, -35, 0)
	single_light.light_energy = 1.2
	add_child(single_light)
	single_light.visible = false
	_reset_camera()
	_show_version()
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.__bedroomReviewQueue=[];window.addEventListener('message',e=>{if(e.origin===location.origin&&e.source===parent&&e.data&&e.data.channel==='elfienest-nest-lab')window.__bedroomReviewQueue.push(e.data);});")

func _show_version() -> void:
	$Snapshot/OriginalBedroomReference.visible = original
	$Snapshot/BedroomFurnitureM01.visible = not original
	caption.text = "单件资产：床 · 拖动旋转 · 滚轮缩放" if single_mode else ("原版 V044" if original else "卧室拆分候选") + " · 静态白天对照 · B 切换原版/候选 · 0 复位"
	scene_button.disabled = not single_mode
	asset_button.disabled = single_mode

func _show_scene() -> void:
	_clear_selection()
	single_mode = false
	single_bed.visible = false
	single_light.visible = false
	$Snapshot.visible = true
	_show_version()
	_reset_camera()

func _show_bed() -> void:
	single_mode = true
	$Snapshot.visible = false
	single_bed.visible = true
	single_light.visible = true
	_show_version()
	_reset_bed_camera()

func _reset_bed_camera() -> void:
	var bounds := AABB()
	var first := true
	for mesh: MeshInstance3D in single_bed.find_children("*", "MeshInstance3D", true, false):
		var box: AABB = mesh.global_transform * mesh.get_aabb()
		bounds = box if first else bounds.merge(box)
		first = false
	if first: return
	target = bounds.get_center()
	var size := maxf(bounds.size.x, maxf(bounds.size.y, bounds.size.z))
	_set_position(target + Vector3(1.15, 0.85, 1.4).normalized() * size * 1.65, 48.0)

func _reset_camera() -> void:
	var floor_mesh: MeshInstance3D
	for mesh: MeshInstance3D in $Snapshot.find_children("*", "MeshInstance3D", true, false):
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("module") == "M01" and str(e.get("source_name", "")).contains("continuous lower floor"):
			floor_mesh = mesh
			break
	assert(floor_mesh != null)
	var walking_y := floor_mesh.get_aabb().end.y
	var frame := floor_mesh.global_transform
	target = frame * Vector3(-0.12, walking_y + 0.95, -0.3)
	_set_position(frame * Vector3(0, walking_y + 1.8, -2.65), 100.0)

func _bed_view(index: int) -> void:
	var bed := $Snapshot/BedroomFurnitureM01.get_node("bed_" + "ABCD"[index]) as Node3D
	target = bed.global_transform * Vector3(-0.05, 0.5, 0.0)
	_set_position(bed.global_transform * Vector3(1.4, 1.35, -2.3), 70.0)

func _set_position(position: Vector3, fov: float) -> void:
	var offset := position - target
	distance = offset.length()
	yaw = atan2(offset.x, offset.z)
	pitch = asin(offset.y / distance)
	camera.fov = fov
	_update_camera()

func _update_camera() -> void:
	camera.global_position = target + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	camera.look_at(target, Vector3.UP)
	camera.make_current()

func _clear_selection() -> void:
	if is_instance_valid(selected_mesh):
		RENDER_BATCHES.restore_before_write(selected_mesh)
		selected_mesh.material_overlay = null
	selected_mesh = null

func _pick_bed(screen_position: Vector2) -> void:
	RENDER_BATCHES.restore_before_write(single_bed, true)
	var origin := camera.project_ray_origin(screen_position)
	var direction := camera.project_ray_normal(screen_position)
	var closest := INF
	var hit_mesh: MeshInstance3D
	for mesh: MeshInstance3D in single_bed.find_children("*", "MeshInstance3D", true, false):
		if not mesh.visible or mesh.mesh == null: continue
		var inverse := mesh.global_transform.affine_inverse()
		var local_origin := inverse * origin
		var local_direction := inverse.basis * direction
		if mesh.get_aabb().intersects_ray(local_origin, local_direction) == null: continue
		if not faces_cache.has(mesh.mesh): faces_cache[mesh.mesh] = mesh.mesh.get_faces()
		var faces: PackedVector3Array = faces_cache[mesh.mesh]
		for index in range(0, faces.size(), 3):
			var hit: Variant = Geometry3D.ray_intersects_triangle(local_origin, local_direction, faces[index], faces[index + 1], faces[index + 2])
			if hit == null: continue
			var hit_distance := origin.distance_squared_to(mesh.global_transform * (hit as Vector3))
			if hit_distance < closest:
				closest = hit_distance
				hit_mesh = mesh
	_clear_selection()
	if hit_mesh != null:
		selected_mesh = hit_mesh
		selected_mesh.material_overlay = selection_material

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_MASK_LEFT:
		yaw -= event.relative.x * 0.006
		pitch = clampf(pitch + event.relative.y * 0.006, -1.4, 1.4)
		_update_camera()
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed: pressed_at = event.position
			elif single_mode and pressed_at.distance_to(event.position) < 5.0: _pick_bed(event.position)
		elif event.pressed:
			if event.button_index == MOUSE_BUTTON_WHEEL_UP: distance = maxf(0.2, distance * 0.9)
			if event.button_index == MOUSE_BUTTON_WHEEL_DOWN: distance = minf(30.0, distance / 0.9)
			_update_camera()
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_B and not single_mode:
			original = not original
			_show_version()
		if event.keycode == KEY_0:
			if single_mode: _reset_bed_camera()
			else: _reset_camera()

func _process(_delta: float) -> void:
	if not OS.has_feature("web"): return
	var messages: Variant = JSON.parse_string(str(JavaScriptBridge.eval("JSON.stringify(window.__bedroomReviewQueue.splice(0))")))
	if messages is Array:
		for message: Dictionary in messages:
			if message.get("type") == "pilot_mode":
				if message.get("mode") == "bed": _show_bed()
				elif message.get("mode") == "scene": _show_scene()
			if message.get("type") == "camera" and str(message.get("action", "")) in ["reset", "select"]:
				if message.get("action") == "reset" or str(message.get("view_id", "")) in ["overview", "dorm-01"]:
					if single_mode: _reset_bed_camera()
					else: _reset_camera()
	if Time.get_ticks_msec() - _last_publish < 500: return
	_last_publish = Time.get_ticks_msec()
	var catalog := {"channel": "elfienest-nest-lab", "kind": "catalog", "views": [{"id": "overview", "label": "卧室拆分试点"}, {"id": "dorm-01", "label": "M01 卧室"}], "active_id": "dorm-01", "presentation_paused": true, "lighting": "lighting-day", "scene_actions": [], "actors": []}
	JavaScriptBridge.eval("parent.postMessage(" + JSON.stringify(catalog) + ",location.origin)")
