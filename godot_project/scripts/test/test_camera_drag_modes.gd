extends SceneTree

var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func drag(nest: ModularNest, button: int, delta: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.button_mask = button
	event.relative = delta
	nest._unhandled_input(event)

func run() -> void:
	var nest := load("res://rooms/nest.tscn").instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	var bridge := NestObserverBridge.new()
	bridge.setup(nest, null, true)
	for left: String in ["look", "orbit"]:
		for right: String in ["track", "free"]:
			var command := {"channel": "elfienest.observer", "version": 1, "kind": "camera_command", "action": "set_drag_modes", "left_drag": left, "right_drag": right}
			check(bridge._parse_camera_command(command).is_empty(), "Removed mode command was accepted")
	bridge.free()
	nest.add_lighting_observer_views()
	check(nest.observer_camera_catalog().active_id == "overview", "Monitor did not default to overview")
	for view: Dictionary in nest._camera_views:
		nest.select_observer_camera_by_id(view.id)
		var camera := nest._active_camera()
		var initial := camera.global_transform
		drag(nest, MOUSE_BUTTON_MASK_LEFT, Vector2(120, 80))
		check(camera.global_position.is_equal_approx(initial.origin), "%s: look moved the camera" % view.id)
		check(not camera.global_basis.is_equal_approx(initial.basis), "%s: look did not turn" % view.id)
		var start := camera.global_position
		drag(nest, MOUSE_BUTTON_MASK_RIGHT, Vector2(0, 400))
		check(camera.global_position.is_equal_approx(start), "%s: vertical track drag moved camera" % view.id)
		drag(nest, MOUSE_BUTTON_MASK_RIGHT, Vector2(100, 0))
		check(not camera.global_position.is_equal_approx(start), "%s: horizontal track drag did not move" % view.id)
		check(is_equal_approx(camera.global_position.y, start.y), "%s: track changed height" % view.id)
		for button: int in [MOUSE_BUTTON_MASK_LEFT, MOUSE_BUTTON_MASK_RIGHT]:
			for delta: Vector2 in [Vector2(5000, 5000), Vector2(-10000, -10000)]:
				drag(nest, button, delta)
				var constrained: Vector3 = nest.call("_constrain_camera_position", camera.global_position)
				check(camera.global_position.is_equal_approx(constrained), "%s: escaped region" % view.id)
		nest.reset_observation_camera()
		check(camera.global_transform.is_equal_approx(initial), "%s: reset changed preset" % view.id)
		check(nest.observer_camera_catalog().active_id == view.id, "Reset switched camera")
	var paused_transform := nest._active_camera().global_transform
	nest.set_observer_presentation_paused(true)
	drag(nest, MOUSE_BUTTON_MASK_LEFT, Vector2(100, 100))
	drag(nest, MOUSE_BUTTON_MASK_RIGHT, Vector2(100, 100))
	check(nest._active_camera().global_transform.is_equal_approx(paused_transform), "Paused input moved camera")
	nest.free()
	print("Fixed camera control checks: %d failures" % failures)
	quit(1 if failures else 0)
