extends Node3D
## Explicit local M01 collision/door review. No authority transport or world clock.

const OPTICAL := preload("res://runtime/lab/m01_optical_sample.gd")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const TOVREN := preload("res://characters/tovren/tovren.tscn")
const STEP_SECONDS := 4.0
const STEP_LABELS := ["白天默认开·演示", "夜间无人关·演示", "胶囊靠近", "胶囊离开", "离开延迟关闭", "关门中重入", "体积占用防夹", "清除后关闭"]

var camera_owner: Node3D
var _sample: Node3D
var _physics: Node3D
var _geometry: Node3D
var _collision_visuals: Node3D
var _door: Dictionary = {}
var _debug: Array[Dictionary] = []
var _actor: CharacterBody3D
var _capsule: CollisionShape3D
var _capsule_frame: Transform3D
var _marker: MeshInstance3D
var _normal := Vector3.FORWARD
var _foot := Vector3.ZERO
var _elapsed := 0.0
var _display := "original"
var _visited: Dictionary = {}
var _last_step := -1
var _demo_default_open := false
var _publish_elapsed := 0.0


static func is_requested() -> bool:
	if not OS.has_feature("web"):
		return false
	var query: Variant = JavaScriptBridge.eval("window.location.search")
	if not query is String:
		return false
	for part in String(query).trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2 and pair[0] == "mode":
			return String(pair[1]).uri_decode() == "collision_review"
	return false


func _ready() -> void:
	if OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('scope')")) == "estate":
		var whole = load("res://runtime/lab/estate_collision_overview.gd").new()
		whole.camera_owner = camera_owner
		add_child(whole)
		set_physics_process(false)
		return
	_sample = OPTICAL.new()
	_sample.set("camera_owner", camera_owner)
	add_child(_sample)
	# The existing HUD owns this review; ignore optical-workbench camera messages.
	_sample.set_process(false)
	_geometry = _sample.get("_geometry") as Node3D
	if not _extract_actual_entry():
		return
	_physics = PHYSICS.new()
	add_child(_physics)
	_physics.call("build", _sample)
	_physics.set_physics_process(false)
	var doors := _physics.get("_doors") as Array
	if doors.size() != 1:
		push_error("Collision review needs exactly the real central/M01 entry")
		set_physics_process(false)
		return
	_door = doors[0]
	_build_collision_visuals()
	_build_capsule()
	var center := _door["center"] as Vector3
	_foot = center - Vector3.UP * 1.2
	var tangent := (_door["offset"] as Vector3).normalized()
	_normal = tangent.cross(Vector3.UP).normalized()
	_sample.call("set_camera", center + _normal * 4.5 + tangent * 3.5 + Vector3.UP * 2.0, center)
	var camera := _sample.get("camera") as Camera3D
	camera_owner.call("configure_collision_review", camera, center, _view_labels())
	camera_owner.connect("observer_camera_catalog_changed", _on_camera_selection)
	_apply_display("original")
	_physics_process(0.0)


func _extract_actual_entry() -> bool:
	var source := (load(OPTICAL.SOURCE) as PackedScene).instantiate() as Node3D
	source.visible = false
	add_child(source)
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if not bool(extras.get("door_leaf", false)) or extras.get("connection", "") != "M01":
			continue
		mesh.reparent(_geometry, true)
		mesh.visible = true
		for index in range(mesh.mesh.get_surface_count()):
			var original := mesh.get_active_material(index) as BaseMaterial3D
			if original != null:
				mesh.set_surface_override_material(index, _sample.call("_optics", original, false))
		source.free()
		return true
	source.free()
	push_error("Authored central/M01 door was not found")
	set_physics_process(false)
	return false


func _build_collision_visuals() -> void:
	_collision_visuals = Node3D.new()
	add_child(_collision_visuals)
	for shape: CollisionShape3D in _physics.find_children("*", "CollisionShape3D", true, false):
		var visual := MeshInstance3D.new()
		visual.mesh = shape.shape.get_debug_mesh()
		_collision_visuals.add_child(visual)
		visual.global_transform = shape.global_transform
		_debug.append({"shape": shape, "visual": visual})


func _build_capsule() -> void:
	var source := TOVREN.instantiate() as CharacterBody3D
	_actor = CharacterBody3D.new()
	_capsule = source.get_node("CollisionShape3D").duplicate() as CollisionShape3D
	_actor.add_child(_capsule)
	source.free()
	add_child(_actor)
	_actor.add_to_group(&"runtime_elfie_actors")
	_capsule_frame = _capsule.transform
	_marker = MeshInstance3D.new()
	_marker.mesh = _capsule.shape.get_debug_mesh()
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(1.0, 0.35, 0.1)
	material.no_depth_test = true
	_marker.material_override = material
	_capsule.add_child(_marker)


func _physics_process(delta: float) -> void:
	if _door.is_empty():
		return
	_elapsed += maxf(delta, 0.0)
	var cycle := fposmod(_elapsed, STEP_SECONDS * STEP_LABELS.size())
	var step := mini(int(cycle / STEP_SECONDS), STEP_LABELS.size() - 1)
	var local_time := fposmod(cycle, STEP_SECONDS)
	_visited[step] = true
	_capsule.transform = _capsule_frame
	_actor.global_position = _foot + _normal * 4.5
	_demo_default_open = step == 0
	match step:
		2:
			_actor.global_position = _foot + _normal * lerpf(4.5, 0.25, minf(local_time / 3.0, 1.0))
		3:
			_actor.global_position = _foot + _normal * lerpf(0.25, 4.5, minf(local_time / 3.0, 1.0))
		5:
			_demo_default_open = local_time < 0.8
			if local_time >= 1.0:
				_actor.global_position = _foot + _normal * 0.25
		6:
			_demo_default_open = local_time < 1.0
			if local_time >= 1.0:
				var occupied := _actor.global_transform
				occupied.origin = _foot
				_capsule.global_transform = occupied * _capsule_frame
	_physics.call("set_door_default_open", _demo_default_open)
	_physics.call("_physics_process", delta)
	_marker.visible = _capsule.global_position.distance_to(_foot) < 3.5
	for item: Dictionary in _debug:
		(item["visual"] as MeshInstance3D).global_transform = (item["shape"] as CollisionShape3D).global_transform
	if step != _last_step:
		_last_step = step
		var hud := camera_owner.get_node("ObservationHUD") as ObservationHUD
		var catalog: Dictionary = camera_owner.call("observer_camera_catalog")
		var selected := str(catalog.get("active_id", "collision-review-0")).trim_prefix("collision-review-").to_int()
		# Existing selector only: no new panel, buttons or layout.
		hud.set_views(_view_labels(), selected)
	_publish_elapsed += delta
	if OS.has_feature("web") and _publish_elapsed >= 0.25:
		_publish_elapsed = 0.0
		JavaScriptBridge.eval("window.__elfienestCollisionReview=" + JSON.stringify(review_state()))


func _view_labels() -> PackedStringArray:
	var phase := str(STEP_LABELS[maxi(_last_step, 0)])
	return PackedStringArray(["原模型｜" + phase, "真实碰撞｜" + phase, "叠加｜" + phase])


func _on_camera_selection(catalog: Dictionary) -> void:
	var id := str(catalog.get("active_id", ""))
	if not id.begins_with("collision-review-"):
		return
	var index := id.trim_prefix("collision-review-").to_int()
	_apply_display(["original", "collision", "overlay"][clampi(index, 0, 2)])


func _apply_display(display: String) -> void:
	_display = display
	_geometry.visible = display != "collision"
	_collision_visuals.visible = display != "original"
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	material.albedo_color = Color(0.1, 1.0, 0.75, 0.55 if display == "overlay" else 1.0)
	if display == "overlay":
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	for item: Dictionary in _debug:
		(item["visual"] as MeshInstance3D).material_override = material


func review_state() -> Dictionary:
	return {"mode": "collision_review", "display": _display, "doors": 1 if not _door.is_empty() else 0, "collision_shapes": _debug.size(), "step": _last_step, "step_label": STEP_LABELS[maxi(_last_step, 0)], "visited_steps": _visited.keys(), "open_amount": _door.get("amount", 0.0), "demo_default_open": _demo_default_open, "world_day_phase_bound": false, "scope": "M01 collision and entry demonstration only; no navigation or actual world phase claim"}
