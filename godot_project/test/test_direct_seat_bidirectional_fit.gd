extends "res://test/test_direct_seat_entry_and_turn.gd"
## Exercise the production candidate search: enter-clear is not exit-clear.

class FitSeatProbe extends "res://runtime/actor/direct_seat_cycle.gd":
	func seat_support(_height: float, _frame: Transform3D) -> Dictionary:
		return {"offset":0.0}

class FitMotionProbe extends RefCounted:
	var actor: ElfieActor
	var start_frame := Transform3D(Basis.IDENTITY,Vector3(0,0,1))
	var end_frame := Transform3D.IDENTITY
	var seated_shapes: Array[Shape3D] = []
	var rise_scale := 1.0
	var arc_clearance := 0.0
	var tail_weight := 0.0
	var last_collider: Node
	var last_obstacle := ""
	var sampled_exit := false
	var exit_queries := 0
	var exit_completed := false
	var matching_shapes := true
	var matching_start := true
	var cancel_during_exit := false
	func _capture() -> Array[Transform3D]: return []
	func _apply(_pose: Array[Transform3D]) -> void: pass
	func sample(amount: float) -> void:
		sampled_exit = false
		actor.global_transform = start_frame.interpolate_with(end_frame,amount)
	func sample_exit(amount: float) -> void:
		sampled_exit = true
		actor.global_transform = end_frame.interpolate_with(start_frame,amount)
	func clear_path(previous: Transform3D, _next: Transform3D, amount: float, leaving: bool = false) -> bool:
		matching_shapes = matching_shapes and leaving == sampled_exit
		if not leaving: return true
		exit_queries += 1
		if cancel_during_exit and amount >= 0.25:
			actor.set("available",false)
			return true
		if amount == 0.0: matching_start = matching_start and previous.is_equal_approx(end_frame)
		# Only exit collides; changing rise/arc cannot fix this narrow seat edge.
		if amount >= 0.25 and end_frame.origin.z < 0.099:
			last_obstacle = "exit thigh / seat edge"
			return false
		if amount == 1.0: exit_completed = true
		return true

func run() -> void:
	var actor := ActorProbe.new(); root.add_child(actor)
	var motion := FitMotionProbe.new(); motion.actor = actor
	var seat := FitSeatProbe.new(); root.add_child(seat); seat.set_process(false)
	seat.actor = actor; seat.motion = motion
	var original := actor.global_transform
	expect(await seat.fit_landing(Transform3D.IDENTITY), "No bidirectionally clear candidate found")
	actor.set_process(false); actor.set_physics_process(false)
	expect(motion.exit_queries > 0 and motion.exit_completed, "Accepted an enter-only candidate")
	expect(motion.matching_shapes and motion.matching_start, "Exit used entrance hulls or the standing sweep origin")
	expect(absf(motion.end_frame.origin.z-0.10) < 0.001, "Search did not reject unsafe exit offsets")
	expect(actor.global_transform.is_equal_approx(original), "Fit search moved the displayed actor")
	var cache: Dictionary = actor.get_meta("seated_fit_cache",{})
	expect(cache.size() == 1, "Failed fit candidates leaked into cache")
	for hint: Dictionary in cache.values():
		expect(absf(hint.offset.y-0.10) < 0.001, "Cache accepted an enter-only candidate")
	# A cached candidate still needs both paths revalidated on reuse.
	motion.end_frame = Transform3D.IDENTITY
	motion.exit_completed = false; motion.exit_queries = 0
	expect(await seat.fit_landing(Transform3D.IDENTITY), "Reused bidirectional candidate failed")
	actor.set_process(false); actor.set_physics_process(false)
	expect(motion.exit_completed and motion.exit_queries > 0, "Cache bypassed exit validation")
	actor.remove_meta("seated_fit_cache")
	motion.end_frame = Transform3D.IDENTITY; motion.cancel_during_exit = true
	expect(not await seat.fit_landing(Transform3D.IDENTITY), "Cancelled exit fit was accepted")
	actor.set_process(false); actor.set_physics_process(false)
	expect(actor.global_transform.is_equal_approx(original), "Cancelled fit left a candidate pose visible")
	expect(not actor.has_meta("seated_fit_cache"), "Cancelled candidate was cached")
	seat.free(); actor.free()
	if failures == 0: print("PASS fit accepts and caches only candidates with complete enter and exit paths")
	quit(1 if failures else 0)
