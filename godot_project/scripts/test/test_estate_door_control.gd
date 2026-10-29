extends SceneTree
## Exercise production motion for eight authored entries and two garden leaves.

const ESTATE := preload("res://rooms/estate/estate.tscn")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const TOVREN := preload("res://characters/tovren/tovren.tscn")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var estate := ESTATE.instantiate() as Node3D
	root.add_child(estate)
	var physics := PHYSICS.new()
	root.add_child(physics)
	physics.build(estate)
	physics.set_physics_process(false)
	var source := TOVREN.instantiate() as CharacterBody3D
	var actor := CharacterBody3D.new()
	var capsule := source.get_node("CollisionShape3D").duplicate() as CollisionShape3D
	actor.add_child(capsule)
	source.free()
	root.add_child(actor)
	actor.add_to_group(&"runtime_elfie_actors")
	var doors: Array = physics.get("_doors")
	if not _require(doors.size() == 10 and doors.filter(func(door: Dictionary) -> bool: return not (door["mesh"] as Node).get_meta("generated_garden_leaf", false)).size() == 8, "Production inventory must retain eight authored entries plus two garden leaves"):
		return
	for door: Dictionary in doors:
		var center: Vector3 = door["center"]
		actor.global_position = center - Vector3.UP * 1.2
		physics._physics_process(0.4)
		if not _require(is_equal_approx(float(door["amount"]), 1.0), "Production approach did not open an actual entry"):
			return
		actor.global_position += Vector3(40, 0, 40)
		physics._physics_process(1.0)
		if not _require(is_equal_approx(float(door["amount"]), 1.0), "Production door closes immediately instead of holding after departure"):
			return
		physics._physics_process(2.0)
		if not _require(is_zero_approx(float(door["amount"])), "Production door does not close after the departure delay"):
			return
		actor.global_position = center - Vector3.UP * 1.2
		physics._physics_process(0.4)
		actor.global_position += Vector3(40, 0, 40)
		physics._physics_process(1.9)
		physics._physics_process(0.2)
		var partially_closed := float(door["amount"])
		if not _require(partially_closed > 0.0 and partially_closed < 1.0, "Production reversal fixture must be closing"):
			return
		actor.global_position = center - Vector3.UP * 1.2
		physics._physics_process(0.1)
		if not _require(float(door["amount"]) > partially_closed, "Production door does not reverse when an actor re-enters"):
			return
		physics._physics_process(0.4)
		# Put the actual capsule in the closing path while its body origin lies
		# outside the proximity radius. Safety must use the shape, not the origin.
		var saved_frame := capsule.transform
		var occupied_frame := capsule.global_transform
		actor.global_position += Vector3(40, 0, 40)
		capsule.global_transform = occupied_frame
		physics._physics_process(3.0)
		if not _require(is_equal_approx(float(door["amount"]), 1.0), "Production door ignores an occupied physical closing sweep"):
			return
		capsule.transform = saved_frame
		physics._physics_process(3.0)
		if not _require(is_zero_approx(float(door["amount"])), "Production door remains stuck after the obstruction leaves"):
			return
		if not _require(_frames_match(door), "Production door mesh and collider transforms diverge"):
			return
	if not _require(physics.has_method("set_door_default_open"), "Production door default needs a narrow externally supplied policy setter"):
		return
	physics.set_door_default_open(true)
	physics._physics_process(0.4)
	for door: Dictionary in doors:
		if not _require(is_equal_approx(float(door["amount"]), 1.0), "Explicit default-open policy did not reach all production entries"):
			return
	physics.set_door_default_open(false)
	physics._physics_process(3.0)
	for door: Dictionary in doors:
		if not _require(is_zero_approx(float(door["amount"])), "Explicit default-closed policy did not reach all production entries"):
			return
	actor.free()
	physics.free()
	estate.free()
	print("PASS: ten production leaves (eight authored + two garden) hold after departure, reverse mid-close, guard actual capsule sweeps, sync colliders and accept external default policy")
	quit(0)


func _frames_match(door: Dictionary) -> bool:
	var frame := (door["mesh"] as Node3D).global_transform
	if frame.basis.determinant() < 0.0:
		frame.basis.x = -frame.basis.x
	return frame.is_equal_approx((door["body"] as Node3D).global_transform)


func _require(condition: bool, message: String) -> bool:
	if not condition:
		push_error(message)
		quit(1)
	return condition
