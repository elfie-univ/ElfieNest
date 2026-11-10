extends SceneTree
const NEST := preload("res://nest/nest.tscn")
const BODY := preload("res://characters/saevi/saevi.tscn")
const CONSOLE := preload("res://runtime/lab/nest_lab_console.gd")
const TIMING := preload("res://nest/estate/estate_platform_cycle.gd")

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var nest := NEST.instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	var characters := Node3D.new()
	root.add_child(characters)
	var body := BODY.instantiate() as ElfieActor
	characters.add_child(body)
	body.configure("preview-actor", Vector3(0, 1, 20))
	body.set_physics_process(false)
	var original := body.global_transform
	var catalog_before := body.elfie_id
	var console := CONSOLE.new()
	root.add_child(console)
	console.setup(nest, characters)
	if not require(console.catalog().scene_actions.any(func(item: Dictionary) -> bool: return item.id == "arrival-platform"), "Complete arrival absent from scene menu"): return
	if not require(not console.camera_command({"action":"scene","target":"arrival-platform","actor_id":"missing"}), "Missing actor accepted"): return
	for replay in range(2):
		body.set_physics_process(replay == 0)
		if not require(console.camera_command({"action":"scene","target":"arrival-platform","actor_id":"preview-actor"}), "Arrival replay rejected"): return
		var preview: Node = console.get("_arrival_preview")
		if not require(preview.running() and console.catalog().active_id == "central-4", "Arrival did not start at actual platform camera"): return
		preview.set_process(false)
		var effects: Node3D = preview.get("_effects")
		var cycle: Node3D = effects.get("_cycle")
		var platform: MeshInstance3D = nest.find_child("Roof01 complete raised landing platform", true, false)
		var bounds := platform.global_transform * platform.get_aabb()
		var center := bounds.get_center()
		var origin := cycle.global_position
		if not require(Vector2(origin.x-center.x, origin.z-center.z).length() < 0.01, "Arrival effect/body must share actual platform center, not the offset activity anchor"): return
		var trajectory := preload("res://runtime/actor/adoption_arrival.gd").new()
		if not require(trajectory.bind(nest) and Vector2(trajectory.origin.x-center.x,trajectory.origin.z-center.z).length() < 0.01, "Physical adoption trajectory must use the same platform center"): return
		var lighting: Node3D = effects.get("_lighting")
		var charge: Node3D = lighting.get("petal_charge")
		print("ARRIVAL_ALIGNMENT platform=",center," effect=",origin," petals=",charge.get("_center"))
		if not require(Vector2(charge.get("_center").x-center.x,charge.get("_center").z-center.z).length() < 0.01, "Petals must rotate around platform center"): return
		for seconds in [0.0,4.0,6.0,8.2,0.0]:
			charge.sample(seconds)
			var angle := -float(charge.get("rotation_angle"))
			var rotation := Transform3D(Basis(Vector3.UP,angle),center-Basis(Vector3.UP,angle)*center)
			for item: Dictionary in charge.get("_moving"):
				if not require((item.mesh as Node3D).global_transform.is_equal_approx(rotation*item.rest), "Petal animation introduced tilt, scale or cumulative drift"): return
		preview._process(6.0)
		if not require(body.global_basis.y.normalized().dot(Vector3.UP) > 0.9999, "Arrival body must stay upright when starting from a lower floor"): return
		if not require(preview.elapsed == 6.0 and body.global_position.y > 9.0, "Production arrival sequence did not advance on fourth floor"): return
		nest.set_observer_presentation_paused(true)
		preview._process(3.0)
		if not require(preview.elapsed == 6.0, "Paused arrival kept advancing"): return
		nest.set_observer_presentation_paused(false)
		preview._process(TIMING.SETTLED_AT)
		if not require(not preview.running() and body.global_transform.is_equal_approx(original) and body.elfie_id == catalog_before and body.is_physics_processing() == (replay == 0), "Replay changed identity or failed to restore actor state"): return
	if not require(not body.has_meta("arrival_id") and not body.has_meta("arrival_started_at"), "Replay wrote admission facts"): return
	console.free()
	characters.free()
	nest.free()
	print("PASS Lab arrival: menu, actual production effect, fourth-floor framing, pause, replay and unchanged actor identity/state")
	quit()
