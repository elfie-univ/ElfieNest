extends SceneTree

class CameraNest extends ModularNest:
	func _ready() -> void:
		pass

var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var nest := CameraNest.new()
	var hud: Node = load("res://ui/observation_hud.tscn").instantiate()
	hud.name = "ObservationHUD"
	nest.add_child(hud)
	root.add_child(nest)
	var overview := Camera3D.new()
	nest.add_child(overview)
	nest._register_observation_view("overview", "Overview", overview, Vector3.ZERO)
	var actor := CharacterBody3D.new()
	root.add_child(actor)
	actor.position = Vector3(3, 0, 2)
	if not nest.has_method("register_observer_actor_camera"):
		push_error("Missing resident follow cameras: residents cannot be located from overview")
		quit(1)
		return
	nest.call("register_observer_actor_camera", "one", actor)
	nest.call("register_observer_actor_camera", "two", actor)
	_check(nest.observation_view_count() == 3, "both resident cameras missing")
	_check(nest.select_observer_camera_by_id("elfie-one"), "resident camera cannot be selected")
	await process_frame
	await process_frame
	var camera := nest._active_camera()
	var initial := camera.global_position
	actor.position += Vector3(2, 0, 1)
	nest._process(1.0 / 60.0)
	_check(camera.global_position.distance_to(initial) < 0.3, "follow camera snapped in a single frame")
	for frame in range(120):
		nest._process(1.0 / 60.0)
	await process_frame
	await process_frame
	_check(camera.global_position.distance_to(initial + Vector3(2, 0, 1)) < 0.01, "camera does not follow locomotion")
	_check(camera.is_position_in_frustum(actor.global_position + Vector3.UP * 0.6), "resident is outside camera frame")
	var wall := StaticBody3D.new()
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(10, 5, 0.2)
	collision.shape = shape
	wall.add_child(collision)
	root.add_child(wall)
	wall.position = actor.position + Vector3(0, 1, 1)
	await physics_frame
	await physics_frame
	nest._process(1.0 / 60.0)
	_check(camera.global_position.z < wall.global_position.z - 0.1, "camera smoothing crosses an occluding wall")
	actor.position.x += 0.5
	nest._process(1.0 / 60.0)
	var gaze := (actor.global_position + Vector3.UP * 0.6 - camera.global_position).normalized()
	_check((-camera.global_basis.z).dot(gaze) > 0.999, "close camera aims at lagging target instead of resident")
	wall.queue_free()
	nest.select_observer_overview()
	await process_frame
	_check(nest.observer_camera_catalog()["active_id"] == "overview", "follow overrides explicit overview selection")
	nest.select_observer_camera_by_id("elfie-one")
	nest.call("remove_observer_actor_camera", "one")
	_check(nest.observer_camera_catalog()["active_id"] == "overview", "removed resident leaves a dangling camera")
	_check(nest.observation_view_count() == 2, "resident camera was not removed")
	actor.queue_free()
	nest.queue_free()
	await process_frame
	for failure in failures:
		push_error(failure)
	if failures.is_empty(): print("PASS resident cameras: selection, movement, framing, overview, removal")
	quit(0 if failures.is_empty() else 1)

func _check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)
