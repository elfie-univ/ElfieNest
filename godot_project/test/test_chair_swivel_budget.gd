extends SceneTree
const SWIVEL := preload("res://runtime/actor/chair_swivel.gd")
var failures := 0

class Passenger extends CharacterBody3D:
	var furniture_cycle_command := "first"
	var available := true
	func cycle_available() -> bool: return available

class Carrier extends "res://runtime/actor/chair_swivel.gd":
	var lag_usec := 0
	var headings: Array[float] = []
	var frames: Array[int] = []
	var passenger_queries := 0
	var reject_at := 0
	func _clock_usec() -> int: return Time.get_ticks_usec()+lag_usec
	func _clear(target: Transform3D, _passenger: CharacterBody3D) -> bool:
		# Deterministic slow-query clock, without blocking or sleeping in the test.
		lag_usec += 40000
		headings.append(target.basis.get_euler().y)
		frames.append(Engine.get_process_frames())
		return reject_at == 0 or headings.size() != reject_at
	func _passenger_clear(_passenger: CharacterBody3D, _next: Transform3D) -> bool:
		lag_usec += 40000
		passenger_queries += 1
		return true

class Pending extends RefCounted:
	var done := false
	var ok := false
	func run(carrier: Node3D, passenger: CharacterBody3D) -> void:
		ok = await carrier.turn_to(0.325,passenger)
		done = true

func _initialize() -> void:
	create_timer(20.0).timeout.connect(func() -> void: push_error("Swivel budget regression timed out"); quit(1))
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func progress(heading: float) -> float:
	# Invert the authored smoothstep to audit simulated-time increments.
	var low := 0.0; var high := 1.0
	for index in range(40):
		var middle := (low+high)*0.5
		if smoothstep(0.0,1.0,middle) < heading/0.325: low = middle
		else: high = middle
	return (low+high)*0.25 # Half-second turn, times midpoint.

func exercise(mode: String) -> void:
	var carrier := Carrier.new(); root.add_child(carrier)
	var passenger := Passenger.new(); root.add_child(passenger)
	passenger.position = Vector3(0,1,1)
	var joint := passenger.transform
	var owned := AnimatableBody3D.new(); carrier.add_child(owned); carrier.bodies.append(owned)
	var preserved := AnimatableBody3D.new(); carrier.add_child(preserved); carrier.bodies.append(preserved)
	passenger.add_collision_exception_with(preserved)
	if mode == "collision": carrier.reject_at = 3
	var pending := Pending.new(); pending.run(carrier,passenger)
	var changed := false
	var saved_chair := Transform3D.IDENTITY
	var saved_passenger := Transform3D.IDENTITY
	while not pending.done:
		await process_frame
		if not pending.done and not changed and carrier.headings.size() > 0 and mode not in ["complete","collision"]:
			changed = true
			match mode:
				"cancel": passenger.available = false
				"command": passenger.furniture_cycle_command = "replacement"
				"target": carrier.position.x += 2.0
				"exit": root.remove_child(carrier)
				"passenger_exit": root.remove_child(passenger)
			saved_chair = carrier.transform
			saved_passenger = passenger.transform
		if carrier.is_inside_tree() and passenger.is_inside_tree() and mode != "target":
			expect(passenger.global_transform.is_equal_approx(carrier.global_transform*joint), "Rendered chair/passenger joint separated")
	expect(pending.ok == (mode == "complete"), "Wrong terminal result: "+mode)
	expect(not carrier.turning, "Turn ownership leaked: "+mode)
	expect(owned not in passenger.get_collision_exceptions(), "Owned collision exception leaked: "+mode)
	expect(preserved in passenger.get_collision_exceptions(), "Removed a pre-existing collision exception")
	if changed:
		expect(carrier.transform.is_equal_approx(saved_chair) and passenger.transform.is_equal_approx(saved_passenger), "Stale turn wrote after owner change: "+mode)
	if mode == "complete":
		expect(carrier.headings.size() == carrier.passenger_queries, "Passenger collision samples were skipped")
		var previous := 0.0
		for index in range(carrier.headings.size()):
			var sample := progress(carrier.headings[index])
			expect(sample >= previous-0.00001 and sample-previous <= 1.0/60.0+0.0001, "Dropped or reordered accumulated turn time")
			if index > 0:
				expect(carrier.frames[index] > carrier.frames[index-1], "Slow batches resumed within the same process frame")
			previous = sample
		expect(absf(previous-0.5) < 0.0001 and absf(carrier.rotation.y-0.325) < 0.00001, "Pending turn progress was lost")
	if mode == "collision":
		expect(carrier.headings.size() == 3 and carrier.passenger_queries == 2, "Queries continued after collision")
		expect(absf(carrier.rotation.y-carrier.headings[1]) < 0.00001, "Blocked sample was committed")
	passenger.free(); carrier.free()

func run() -> void:
	expect(SWIVEL.work_budget_usec(0.008) == 8000, "Wrong minimum budget")
	expect(SWIVEL.work_budget_usec(0.1) == 50000, "Wrong half-frame budget")
	expect(SWIVEL.work_budget_usec(0.5) == 64000, "Wrong maximum budget")
	for mode: String in ["complete","collision","cancel","command","target","exit","passenger_exit"]:
		await exercise(mode)
	if failures == 0: print("PASS swivel render-frame budget, ordered collision samples, owner cancellation and exception restoration")
	quit(1 if failures else 0)
