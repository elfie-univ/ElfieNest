extends Node3D
## Explicit M01 camera review. Targets are local fixtures, not world residents.

const OPTICAL := preload("res://runtime/lab/m01_optical_sample.gd")
const FIXED_REVIEW := preload("res://runtime/lab/estate_fixed_camera_review.gd")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const BOUNDS := preload("res://runtime/lab/camera_review_bounds.gd")
const TOVREN_PATH := "res://characters/tovren/tovren.tscn"
const FIXED_LABELS := ["M01默认构图", "候选左界·近", "候选右界·远", "复位M01"]

var camera_owner: Node3D
var _sample: Node3D
var _physics: Node3D
var _bounds: RefCounted
var _actor_a: ElfieActor
var _actor_b: ElfieActor
var _floor_frame := Transform3D.IDENTITY
var _floor_y := 0.0
var _floor_source_node := ""
var _a_position := Vector3.ZERO
var _b_position := Vector3.ZERO
var _wall_point := Vector3.ZERO
var _wall_source := ""
var _ready_for_review := false
var _last_view := ""
var _publish_elapsed := 0.0


static func is_requested() -> bool:
	return OPTICAL.is_requested("camera_review")

func _ready() -> void:
	if FIXED_REVIEW.is_requested():
		var fixed := FIXED_REVIEW.new()
		fixed.name = "FixedCatalogLocalGeometryReview"
		fixed.camera_owner = camera_owner
		add_child(fixed)
		return
	_sample = OPTICAL.new()
	_sample.set("camera_owner", camera_owner)
	add_child(_sample)
	# This review uses the existing HUD, not the optical workbench message queue.
	_sample.set_process(false)
	_floor_frame = _sample.get("_floor_frame")
	for mesh: MeshInstance3D in _sample.find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if str(extras.get("source_name", "")).contains("continuous lower floor"):
			_floor_y = (mesh.global_transform * mesh.get_aabb()).end.y + 0.02
			_floor_source_node = str(mesh.name)
			break
	var camera := _sample.get("camera") as Camera3D
	camera_owner.call("configure_camera_review", camera, camera_owner.get("_camera_target"), PackedStringArray(FIXED_LABELS))
	_bounds = BOUNDS.new(camera_owner, camera)
	_physics = PHYSICS.new()
	add_child(_physics)
	_physics.call("build", _sample)
	_physics.set_physics_process(false)
	var origin := _floor_frame.origin
	origin.y = _floor_y
	_actor_a = _make_actor("review-a", origin, "A")
	_actor_b = _make_actor("review-b", origin, "B")
	camera_owner.call("register_observer_actor_camera", "review-a", _actor_a)
	camera_owner.call("register_observer_actor_camera", "review-b", _actor_b)
	camera_owner.call("register_observer_actor_camera", "review-wall", _actor_a)
	var views := camera_owner.get("_camera_views") as Array
	views[-3]["label"] = "跟随目标 A"
	views[-2]["label"] = "跟随目标 B"
	views[-1]["label"] = "实际M01墙遮挡"
	var hud := camera_owner.get_node("ObservationHUD") as ObservationHUD
	hud.set_views(camera_owner.call("observation_view_labels"), 0)
	camera_owner.connect("observer_camera_catalog_changed", _on_camera_selection)
	camera_owner.call("select_observer_camera_by_id", "overview")
	_prepare_targets.call_deferred()


func _make_actor(id: String, position: Vector3, label: String) -> ElfieActor:
	var actor := (load(TOVREN_PATH) as PackedScene).instantiate() as ElfieActor
	add_child(actor)
	actor.configure(id, position)
	actor.set_physics_process(false)
	(actor.get_node("NavigationAgent3D") as NavigationAgent3D).avoidance_enabled = false
	actor.visible = false
	var identifier := Label3D.new()
	identifier.text = label
	identifier.position.y = 1.5
	identifier.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	actor.add_child(identifier)
	return actor


func _prepare_targets() -> void:
	await get_tree().physics_frame
	await get_tree().physics_frame
	if not is_instance_valid(_actor_a):
		return
	var candidates: Array[Vector3] = []
	for x: float in [0.0, -0.8, 0.8, -1.6, 1.6, -2.4, 2.4, -3.2, 3.2]:
		for z: float in [0.0, -0.8, 0.8, -1.6, 1.6, -2.4, 2.4, -3.2, 3.2]:
			var point := _floor_frame * Vector3(x, 0.0, z)
			point.y = _floor_y
			if _is_clear_supported_point(point):
				candidates.append(point)
	if candidates.size() < 2:
		push_error("Camera review could not find two actual supported M01 target positions")
		return
	_a_position = candidates[0]
	for candidate in candidates:
		if candidate.distance_to(_a_position) > 0.8:
			_b_position = candidate
			break
	if _b_position == Vector3.ZERO:
		push_error("Camera review targets cannot be safely separated")
		return
	_actor_a.global_position = _a_position
	_actor_b.global_position = _b_position
	_actor_a.ground_visual_to_floor(_floor_y)
	_actor_b.ground_visual_to_floor(_floor_y)
	_actor_a.visible = true
	_actor_b.visible = true
	for candidate in candidates:
		if candidate.distance_to(_b_position) < 0.7:
			continue
		var target := candidate + Vector3.UP * 0.6
		var query := PhysicsRayQueryParameters3D.create(target, target + Vector3(1.8, 1.0, 2.2))
		query.exclude = _actor_rids()
		var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if hit.is_empty() or target.distance_to(hit["position"]) < 0.35:
			continue
		var collider := hit["collider"] as Node
		var source := str(collider.get_meta("source_node", "")).to_lower()
		if not ("wall" in source or "shell" in source or "glass" in source):
			continue
		_wall_point = candidate
		_wall_source = str(collider.get_meta("source_node", ""))
		break
	_ready_for_review = not _wall_source.is_empty()
	if not _ready_for_review:
		push_error("Camera review found no actual M01 wall occlusion; no fake wall was added")
	else:
		_last_view = ""
		_on_camera_selection(camera_owner.call("observer_camera_catalog"))


func _is_clear_supported_point(point: Vector3) -> bool:
	var space := get_world_3d().direct_space_state
	var ground := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 0.2, point - Vector3.UP * 0.15)
	ground.exclude = _actor_rids()
	var support := space.intersect_ray(ground)
	if support.is_empty():
		return false
	var source := str((support["collider"] as Node).get_meta("source_node", ""))
	if source != _floor_source_node:
		return false
	var capsule := _actor_a.get_node("CollisionShape3D") as CollisionShape3D
	var frame := _actor_a.global_transform
	frame.origin = point
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = capsule.shape
	query.transform = frame * capsule.transform
	query.exclude = _actor_rids()
	return space.intersect_shape(query, 1).is_empty()


func _actor_rids() -> Array[RID]:
	return [_actor_a.get_rid(), _actor_b.get_rid()]


func _on_camera_selection(catalog: Dictionary) -> void:
	var id := str(catalog.get("active_id", ""))
	if id == _last_view:
		return
	_last_view = id
	if _ready_for_review:
		_actor_a.global_position = _wall_point if id == "elfie-review-wall" else _a_position
	if id == "camera-review-left":
		_bounds.call("set_candidate", -30.0, 0.0, 34.0)
	elif id == "camera-review-right":
		_bounds.call("set_candidate", 30.0, 10.0, 60.0)
	elif id in ["overview", "camera-review-reset"]:
		_bounds.call("reset")
	if id.begins_with("elfie-"):
		var views := camera_owner.get("_camera_views") as Array
		var active := int(camera_owner.get("_active_camera_index"))
		views[active]["follow_initialized"] = false
		camera_owner.call("_process", 0.0)


func _process(delta: float) -> void:
	if _bounds == null:
		return
	var catalog: Dictionary = camera_owner.call("observer_camera_catalog")
	var id := str(catalog.get("active_id", ""))
	if not id.begins_with("elfie-"):
		_bounds.call("clamp_current")
	_publish_elapsed += delta
	if OS.has_feature("web") and _publish_elapsed >= 0.25:
		_publish_elapsed = 0.0
		JavaScriptBridge.eval("window.__elfienestCameraReview=" + JSON.stringify(review_state()))


func _wall_camera_clear() -> bool:
	var catalog: Dictionary = camera_owner.call("observer_camera_catalog")
	if not _ready_for_review or catalog.get("active_id") != "elfie-review-wall":
		return false
	var camera := camera_owner.call("_active_camera") as Camera3D
	var target := _actor_a.global_position + Vector3.UP * 0.6
	var query := PhysicsRayQueryParameters3D.create(target, camera.global_position)
	query.exclude = _actor_rids()
	return get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func review_state() -> Dictionary:
	return {"mode": "camera_review", "ready": _ready_for_review, "actual_wall_found": not _wall_source.is_empty(), "actual_wall_source": _wall_source, "wall_camera_clear": _wall_camera_clear() if _bounds != null else false, "candidate_limits": _bounds.call("limits") if _bounds != null else {}, "scope": "local camera fixtures only; no world residents, navigation acceptance or role-animation edits"}
