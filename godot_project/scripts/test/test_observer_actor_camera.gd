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
	var body := MeshInstance3D.new()
	body.mesh = BoxMesh.new()
	body.layers = 3
	actor.add_child(body)
	if not nest.has_method("register_observer_actor_camera"):
		push_error("Missing resident follow cameras: residents cannot be located from overview")
		quit(1)
		return
	nest.call("register_observer_actor_camera", "one", actor)
	nest.call("register_observer_actor_camera", "two", actor)
	_check(nest.observation_view_count() == 5, "both resident cameras missing")
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
	wall.position = actor.position + Vector3(0, 1, 0.4)
	await physics_frame
	await physics_frame
	for frame in range(120):
		nest._process(1.0 / 60.0)
	var follow_target := actor.global_position + Vector3.UP * 0.6
	_check(camera.global_position.distance_to(follow_target) >= 1.8, "close wall squeezed follow camera into resident")
	_check(camera.is_position_in_frustum(actor.global_position + Vector3.UP * 1.6), "close wall cropped resident head")
	_check(camera.is_position_in_frustum(actor.global_position + Vector3.UP * 0.1), "close wall cropped resident feet")
	var side_wall := StaticBody3D.new()
	var side_collision := CollisionShape3D.new()
	var side_shape := BoxShape3D.new()
	side_shape.size = Vector3(0.2, 5, 10)
	side_collision.shape = side_shape
	side_wall.add_child(side_collision)
	root.add_child(side_wall)
	side_wall.position = actor.position + Vector3(0.4, 1, 0)
	await physics_frame
	await physics_frame
	for frame in range(120):
		nest._process(1.0 / 60.0)
	_check(camera.global_position.distance_to(follow_target) >= 1.8, "corner squeezed follow camera into resident")
	_check(camera.global_position.x < side_wall.global_position.x - 0.1, "camera crossed the corner wall")
	var safe_position := camera.global_position
	for frame in range(60):
		nest._process(1.0 / 60.0)
	_check(camera.global_position.distance_to(safe_position) < 0.01, "stationary corner camera keeps changing sides")
	side_wall.queue_free()
	wall.queue_free()
	nest.select_observer_overview()
	await process_frame
	_check(nest.observer_camera_catalog()["active_id"] == "overview", "follow overrides explicit overview selection")
	_check(nest.select_observer_camera_by_id("elfie-pov-one"), "first-person camera missing")
	nest._process(0.0)
	var eye_camera := nest._active_camera()
	_check(body.layers == 1 << 19 and not eye_camera.get_cull_mask_value(20), "first person sees its own body")
	_check(body.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON, "first person disabled body shadows")
	_check(eye_camera.global_position.distance_to(actor.global_position) < 2.0, "first person is not at actor head")
	var eye_before := eye_camera.global_position
	actor.position += Vector3(1, 0, 0)
	nest._process(0.0)
	_check(eye_camera.global_position.is_equal_approx(eye_before + Vector3.RIGHT), "first-person camera did not move with actor")
	var input := InputEventMouseMotion.new()
	input.button_mask = MOUSE_BUTTON_MASK_RIGHT
	input.relative = Vector2(100, 100)
	nest._unhandled_input(input)
	_check(eye_camera.global_position.is_equal_approx(eye_before + Vector3.RIGHT), "first-person right drag detached from actor")
	input.button_mask = MOUSE_BUTTON_MASK_LEFT
	var heading := eye_camera.global_basis
	nest._unhandled_input(input)
	_check(not eye_camera.global_basis.is_equal_approx(heading), "first-person left drag did not turn head")
	nest.reset_observation_camera()
	_check(eye_camera.global_basis.is_equal_approx(heading), "first-person reset did not restore actor heading")
	nest.select_observer_camera_by_id("elfie-one")
	_check(body.layers == 3, "leaving first person did not restore body layers")
	nest.call("remove_observer_actor_camera", "one")
	_check(nest.observer_camera_catalog()["active_id"] == "overview", "removed resident leaves a dangling camera")
	_check(nest.observation_view_count() == 3, "resident camera was not removed")
	actor.queue_free()
	nest.queue_free()
	await process_frame
	for failure in failures:
		push_error(failure)
	if failures.is_empty(): print("PASS resident cameras: selection, movement, framing, overview, removal")
	quit(0 if failures.is_empty() else 1)

func _check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)
