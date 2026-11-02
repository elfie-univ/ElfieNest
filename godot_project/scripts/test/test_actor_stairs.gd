extends SceneTree

## Tiny real-physics regression: only Saevi and primitive collision fixtures.
## No complete estate, main scene, manual floor-Y correction or fake terminal.
const SAEVI := preload("res://characters/saevi/saevi.tscn")
var _errors: Array[String] = []


func _init() -> void:
	call_deferred("run")


func run() -> void:
	await _case("entry_three_treads", Vector3(0.44, 0.168417, 0), Vector3(2.5, 0.32, 0))
	await _case("ground_up", Vector3(-1.5, 0.02, 0), Vector3(2.5, 0.32, 0))
	await _case("down_to_ground", Vector3(2.5, 0.32, 0), Vector3(-1.5, 0.02, 0))
	await _case("wall_not_climbed", Vector3(-1.5, 0.02, 0), Vector3(2.5, 0.32, 0), "wall")
	await _case("low_ceiling", Vector3(-1.5, 0.02, 0), Vector3(2.5, 0.32, 0), "ceiling")
	await _case("full_size_capsule", Vector3(0.32, 0.168417, 0), Vector3(2.5, 0.32, 0), "", true)
	await _case("narrow_real_risers", Vector3(-1.5, 0.02, 0), Vector3(3.4, 1.42, 0), "", true, true)
	if not _errors.is_empty():
		for error in _errors:
			push_error(error)
		quit(1)
		return
	print("PASS actor stairs: real Saevi, .15/.24/.30 ascent/descent, wall and low-ceiling sweeps")
	quit(0)


func _case(
	id: String, start: Vector3, goal: Vector3, blocker: String = "",
	full_size: bool = false, narrow: bool = false,
) -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	_box(stage, "Ground", Vector3(8, 0.1, 4), Vector3(0, -0.05, 0))
	if narrow:
		for tread in range(9):
			var height := 1.4 / 9.0 * (tread + 1)
			_box(stage, "NarrowTread%d" % tread, Vector3(0.26, height, 4), Vector3(0.26 * (tread + 0.5), height * 0.5, 0))
		_box(stage, "Landing", Vector3(1.66, 1.4, 4), Vector3(3.17, 0.7, 0))
	else:
		_box(stage, "LowerTread", Vector3(0.65, 0.15, 4), Vector3(0.325, 0.075, 0))
		_box(stage, "UpperTread", Vector3(0.65, 0.24, 4), Vector3(0.975, 0.12, 0))
		_box(stage, "Landing", Vector3(2.7, 0.30, 4), Vector3(2.65, 0.15, 0))
	var actor := SAEVI.instantiate() as ElfieActor
	actor.install_shared_animations = false
	stage.add_child(actor)
	actor.configure(id, start)
	var collision := actor.get_node("CollisionShape3D") as CollisionShape3D
	var capsule := collision.shape as CapsuleShape3D
	if not is_equal_approx(capsule.radius, 0.34) or not is_equal_approx(capsule.height, 1.72):
		_errors.append("%s changed the real Saevi capsule" % id)
		stage.queue_free()
		await process_frame
		return
	if full_size:
		collision.scale = Vector3.ONE
		collision.position.y = capsule.height * 0.5
	var body_height := capsule.height * collision.scale.y
	# Isolate physical stepping from Recast/map synchronization. A fixture goal
	# drives the unchanged Actor physics; no floor Y or terminal is fabricated.
	actor.set_physics_process(false)
	var agent := actor.get_node("NavigationAgent3D") as NavigationAgent3D
	agent.avoidance_enabled = false
	var roof_bottom := body_height + 0.21
	if blocker == "wall":
		_box(stage, "Wall", Vector3(0.2, 3, 4), Vector3(-0.15, 1.5, 0))
	elif blocker == "ceiling":
		_box(stage, "LowCeiling", Vector3(3.5, 0.2, 4), Vector3(1.5, roof_bottom + 0.1, 0))
	await physics_frame
	await physics_frame
	var terminals: Array[Dictionary] = []
	actor.navigation_terminal.connect(
		func(command: String, status: String, reason: String) -> void:
			terminals.append({"command": command, "status": status, "reason": reason})
	)
	var maximum_y := actor.global_position.y
	var minimum_y := actor.global_position.y
	var ceiling_penetration := false
	actor.active_command_id = id
	actor.set("_deadline_msec", Time.get_ticks_msec() + 12000)
	actor.set("_navigation_path", PackedVector3Array([start, goal]))
	actor.set("_navigation_path_index", 1)
	agent.target_position = goal
	if true:
		for _frame in range(720):
			await physics_frame
			actor._physics_process(1.0 / 60.0)
			if not actor.active_command_id.is_empty():
				var drive := goal - actor.global_position
				drive.y = 0.0
				actor._on_avoidance_velocity_computed(drive.normalized() * ElfieActor.WALK_SPEED)
			maximum_y = maxf(maximum_y, actor.global_position.y)
			minimum_y = minf(minimum_y, actor.global_position.y)
			if blocker == "ceiling" and actor.global_position.x > -0.25:
				ceiling_penetration = ceiling_penetration or actor.global_position.y + body_height > roof_bottom + 0.025
			if not terminals.is_empty():
				break
		var completed: bool = terminals.size() == 1 and terminals[0]["status"] == "completed"
		var reached := actor.global_position.distance_to(goal) <= ElfieActor.ARRIVAL_DISTANCE * 2.0
		if blocker.is_empty():
			if not completed or not reached or minimum_y < -0.025:
				_diagnose(actor, goal)
				_errors.append("%s failed physical traversal: position=%s floor=%s terminal=%s" % [
					id, actor.global_position, actor.is_on_floor(), terminals])
		else:
			if terminals.size() != 1 or terminals[0]["status"] != "failed" or reached:
				_errors.append("%s did not terminate as a real blocked move: %s" % [id, terminals])
			if blocker == "wall" and (actor.global_position.x >= -0.20 or maximum_y > 0.20):
				_errors.append("Actor climbed or crossed a blocking wall")
			if blocker == "ceiling" and ceiling_penetration:
				_errors.append("Actor penetrated a low ceiling during step-up")
		print("STAIR_CASE ", id, " position=", actor.global_position, " y_range=", Vector2(minimum_y, maximum_y), " terminal=", terminals)
	stage.queue_free()
	await process_frame
	await physics_frame


func _box(parent: Node3D, id: String, size: Vector3, center: Vector3) -> void:
	var body := StaticBody3D.new()
	body.name = id
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	parent.add_child(body)
	body.global_position = center


func _diagnose(actor: ElfieActor, goal: Vector3) -> void:
	var direction := goal - actor.global_position
	direction.y = 0.0
	var motion := direction.normalized() * ElfieActor.WALK_SPEED * actor.get_physics_process_delta_time()
	var forward_hit := KinematicCollision3D.new()
	var up_hit := KinematicCollision3D.new()
	var down_hit := KinematicCollision3D.new()
	var lift := Vector3.UP * (ElfieActor.MAX_STEP_HEIGHT + actor.safe_margin)
	var raised := actor.global_transform
	raised.origin += lift + motion
	var capsule := (actor.get_node("CollisionShape3D") as CollisionShape3D)
	var probe := raised
	var probe_motion := direction.normalized() * (capsule.shape as CapsuleShape3D).radius * capsule.global_basis.get_scale().x
	probe.origin += probe_motion
	var tread := KinematicCollision3D.new()
	var raised_forward := raised
	raised_forward.origin -= motion
	var forward_exact := KinematicCollision3D.new()
	var exact_hit := actor.test_move(actor.global_transform, motion, forward_exact, actor.safe_margin)
	var probe_hit := actor.test_move(probe, -lift - Vector3.UP * actor.safe_margin, tread)
	print("STEP_DIAGNOSTIC floor=", actor.is_on_floor(),
		" delta=", actor.get_physics_process_delta_time(), " vel_y=", actor.velocity.y,
		" exact_forward=", exact_hit, " exact_normal=", forward_exact.get_normal() if exact_hit else Vector3.ZERO,
		" forward=", actor.test_move(actor.global_transform, motion, forward_hit),
		" up=", actor.test_move(actor.global_transform, lift, up_hit),
		" down=", actor.test_move(raised, -lift - Vector3.UP * actor.safe_margin, down_hit),
		" down_normal=", down_hit.get_normal(), " rise=", (raised.origin + down_hit.get_travel()).y - actor.global_position.y,
		" raised_forward=", actor.test_move(raised_forward, motion),
		" probe_forward=", actor.test_move(raised, probe_motion),
		" probe_down=", probe_hit, " probe_normal=", tread.get_normal(),
		" probe_rise=", (probe.origin + tread.get_travel()).y - actor.global_position.y,
		" actual_step=", actor._try_step_up(motion))
