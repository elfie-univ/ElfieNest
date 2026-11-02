extends SceneTree

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var nest := load("res://rooms/nest.tscn").instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	await process_frame
	for spec: Array in [["central-1",0.55,3.81],["central-2",4.55,6.61],["central-3",7.35,9.41]]:
		nest.select_observer_camera_by_id(spec[0])
		for buttons: int in [MOUSE_BUTTON_MASK_LEFT,MOUSE_BUTTON_MASK_RIGHT]:
			for delta: Vector2 in [Vector2(2000,2000),Vector2(-4000,-4000),Vector2(2000,2000)]:
				var event := InputEventMouseMotion.new()
				event.button_mask=buttons
				event.relative=delta
				nest._unhandled_input(event)
				if not inside(nest,spec): return
		for button: int in [MOUSE_BUTTON_WHEEL_UP,MOUSE_BUTTON_WHEEL_DOWN]:
			for step in range(30):
				var event := InputEventMouseButton.new()
				event.button_index=button
				event.pressed=true
				nest._unhandled_input(event)
				if not inside(nest,spec): return
		nest.reset_observation_camera()
		if not inside(nest,spec): return
	nest.select_observer_overview()
	if nest._active_camera().global_position.y<10.0:
		push_error("Indoor limits leaked into overview")
		quit(1)
		return
	nest.free()
	print("PASS floor camera: orbit, pan, zoom, reset, floor switch and unrestricted overview")
	quit(0)

func inside(nest: ModularNest,spec: Array) -> bool:
	for y: float in [nest.to_local(nest._active_camera().global_position).y,nest.to_local(nest._camera_target).y]:
		if y<float(spec[1])-0.001 or y>float(spec[2])+0.001:
			push_error("Camera/target escaped selected floor %s: %f" % [spec[0],y])
			quit(1)
			return false
	return true
