extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var nest := load("res://rooms/nest.tscn").instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	if not require(nest.bake_navigation(), "Complete estate navigation must load"): return
	if not require(await nest.wait_for_navigation_sync(), "Navigation must synchronize"): return
	var anchor := nest.resolve_anchor("central-04/activity")
	if not require(anchor != null, "Fourth-floor activity anchor must exist"): return
	if not require(nest.validate_navigation_anchors(), "Every semantic anchor must reach the courtyard"): return
	if not require(absf(anchor.global_position.y - 9.92) < 0.16, "Roof activity must stay on its walking floor, not the raised arrival apparatus"): return
	print("PASS estate activity anchors: authored fourth-floor surface and all routes to courtyard")
	quit(0)
