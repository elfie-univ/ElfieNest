extends "res://test/test_observer_actor_camera.gd"

func run() -> void:
	var console := load("res://runtime/lab/nest_lab_console.gd") as GDScript
	if not console.has_method("valid_live_environment"):
		push_error("Lab lighting must accept the Nest-owned projection")
		quit(1)
		return
	_check(console.valid_live_environment({"phase":"dusk", "lights_on":true,"quiet_mode":false}), "Lab rejects Nest evening projection")
	_check(not console.valid_live_environment({"phase":"invalid", "lights_on":true,"quiet_mode":false}), "Lab accepts unknown phase")
	_check(not console.valid_live_environment({"phase":"night", "lights_on":"true","quiet_mode":true}), "Lab accepts malformed environment")
	await super.run()
