extends SceneTree
## Delayed first synchronization must defer, then perform, the real projection.

class MotionProbe extends RefCounted:
	var furniture_cycle_command := "startup-seat"
	var cycle_cancelled := false

class ActorProbe extends ElfieActor:
	func _ready() -> void:
		_furniture_motion = MotionProbe.new()
		set_process(false)
		set_physics_process(false)
	func cycle_available() -> bool:
		return not cycle_cancelled

class SeatProbe extends "res://runtime/actor/direct_seat_cycle.gd":
	var walked: Array[Vector3] = []
	func walk_segment(point: Vector3) -> bool:
		walked.append(point)
		return available()

class Pending extends RefCounted:
	var done := false
	var accepted := false
	func project(seat: Node) -> void:
		accepted = await seat._project_waiting()
		done = true
	func walk(seat: Node, point: Vector3) -> void:
		accepted = await seat.walk(point)
		done = true

func _initialize() -> void:
	create_timer(15.0).timeout.connect(func() -> void: push_error("Navigation readiness regression timed out"); quit(1))
	call_deferred("run")

func check(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	# A separate empty world keeps the test independent of the estate bake.
	var viewport := SubViewport.new(); viewport.world_3d = World3D.new(); root.add_child(viewport)
	var actor := ActorProbe.new()
	var visual := Node3D.new(); visual.name = "VisualRoot"; actor.add_child(visual)
	var collision := CollisionShape3D.new(); collision.name = "CollisionShape3D"; actor.add_child(collision)
	var player := AnimationPlayer.new(); player.name = "AnimationPlayer"; actor.add_child(player)
	viewport.add_child(actor)
	actor.position = Vector3(1.5, 0.02, 1.0)
	var seat := SeatProbe.new(); viewport.add_child(seat); seat.set_process(false); seat.actor = actor
	var map := actor.get_world_3d().navigation_map
	NavigationServer3D.map_set_active(map, false)
	if not check(NavigationServer3D.map_get_iteration_id(map) == 0, "Fixture map already synchronized"): return
	seat.waiting.origin = Vector3(0.9, 0.02, 1.0)
	var original := seat.waiting
	var pending := Pending.new(); pending.project(seat)
	var walking := Pending.new(); walking.walk(seat, Vector3(2.5, 0.02, 1.0))
	for frame in range(3): await physics_frame
	if not check(not pending.done and not walking.done and seat.walked.is_empty() and seat.waiting == original, "Unsynchronized map queried or projection skipped"): return
	# Synchronizing an empty map still supplies no owner for the intended point.
	NavigationServer3D.map_set_active(map, true)
	for frame in range(3): await physics_frame
	if not check(not pending.done and not walking.done, "Empty map treated as navigable"): return
	var mesh := NavigationMesh.new()
	mesh.set_vertices(PackedVector3Array([Vector3(1,0,0),Vector3(1,0,2),Vector3(3,0,2),Vector3(3,0,0)]))
	mesh.add_polygon(PackedInt32Array([0,1,2,3]))
	var region := NavigationServer3D.region_create()
	NavigationServer3D.region_set_navigation_mesh(region, mesh)
	NavigationServer3D.region_set_map(region, map)
	for frame in range(120):
		if pending.done and walking.done: break
		await physics_frame
	if not check(pending.done and pending.accepted and walking.done and walking.accepted, "Ready navigation did not resume seat work"): return
	if not check(is_equal_approx(seat.waiting.origin.x, 1.0) and is_equal_approx(seat.waiting.origin.y, original.origin.y), "Original waiting-point projection was not performed"): return
	if not check(not seat.walked.is_empty() and seat.walked.back() == Vector3(2.5,0.02,1.0), "Intended walking destination lost"): return
	NavigationServer3D.map_set_active(map, false)
	for frame in range(2): await physics_frame
	for stop: String in ["cancel", "command", "actor", "controller"]:
		seat.waiting = original
		pending = Pending.new(); pending.project(seat)
		if not check(not pending.done, "Inactive navigation did not wait"): return
		match stop:
			"cancel": actor._furniture_motion.cycle_cancelled = true
			"command": actor._furniture_motion.furniture_cycle_command = "replacement-seat"
			"actor": viewport.remove_child(actor)
			"controller": viewport.remove_child(seat)
		for frame in range(3): await physics_frame
		if not check(pending.done and not pending.accepted and seat.waiting == original, "Stale/cancelled owner resumed projection: " + stop): return
		if not actor.is_inside_tree(): viewport.add_child(actor)
		if not seat.is_inside_tree(): viewport.add_child(seat)
		actor._furniture_motion.cycle_cancelled = false
		actor._furniture_motion.furniture_cycle_command = "startup-seat"
	NavigationServer3D.free_rid(region)
	viewport.free()
	print("PASS direct seat waits for synchronized navigation owner, projects, routes and cancels stale work")
	quit(0)
