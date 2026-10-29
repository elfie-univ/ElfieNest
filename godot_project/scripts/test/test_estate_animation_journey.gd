extends SceneTree

class EmptyPhysics extends Node3D:
	var loaded_precompiled := false

class UnreadyNest extends Node3D:
	var _estate_physics: Node3D
	func set_observation_hud_visible(_visible: bool) -> void: pass

class LoadingNest extends Node3D:
	var _estate_physics: Node3D

class DoorPhysics extends Node3D:
	var _doors: Array[Dictionary] = []

class DoorWorld extends Node3D:
	var physics: Node3D

class DoorJourney extends "res://runtime/lab/estate_animation_journey.gd":
	var visited: Array[String] = []
	func _walk_anchor(id: String) -> bool:
		visited.append(id)
		return true
	func _wait(_seconds: float, _sample: Callable = Callable()) -> void: pass


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	if OS.get_environment("ELFIENEST_JOURNEY_TEST_CASE") == "doors":
		if await representative_door(): quit(0)
		return
	if OS.get_environment("ELFIENEST_JOURNEY_TEST_CASE") == "locomotion":
		if journey_locomotion(): quit(0)
		return
	if OS.get_environment("ELFIENEST_JOURNEY_TEST_CASE") == "bed":
		if await bed_handoff(): quit(0)
		return
	var source := load("res://runtime/lab/estate_animation_journey_plan.gd") as GDScript
	if source == null:
		push_error("Missing continuous animation journey plan")
		quit(1)
		return
	var plan: RefCounted = source.new()
	assert(source.auto_start("?mode=animation_journey&autoplay=1"))
	assert(not source.auto_start("?mode=animation_journey"))
	assert(not source.auto_start("?observer=product&autoplay=1"))
	plan.start()
	assert(plan.current()["id"] == "arrival")
	assert(plan.finish_current(true, "", Vector3.ZERO))
	assert(plan.current()["id"] == "platform-exit")
	var actual := Vector3(0.2, 10.4, 1.3)
	assert(not plan.finish_current(false, "physical stair blocked", actual))
	assert(not plan.running)
	assert(plan.completed == ["arrival"])
	assert(plan.blocked["position"] == [actual.x, actual.y, actual.z])
	# A stray late completion must never advance a failed chapter.
	assert(not plan.finish_current(true, "", Vector3.ZERO))
	assert(plan.current()["id"] == "platform-exit")
	assert(plan.report()["pending"].size() == source.STAGES.size() - 1)
	assert(plan.retry_current())
	assert(plan.current()["id"] == "platform-exit")
	assert(plan.finish_current(true, "", actual))
	assert(plan.current()["id"] == "stairs")
	var ids: Array[String] = []
	for stage: Dictionary in source.STAGES:
		assert(not ids.has(stage["id"]))
		ids.append(stage["id"])
	for required: String in ["doors", "garden-door", "locomotion", "expressions", "chair", "sofa-central", "sofa-cinema", "sofa-tea", "sleep-back", "sleep-left", "sleep-right", "embodiment", "fountain", "spillway", "lake", "water-night", "clip-inventory"]:
		assert(ids.has(required), "Unscheduled animation group: " + required)
	assert(source.clip_sources().size() == 25)
	for path: String in source.clip_sources().values():
		assert(ResourceLoader.exists(path), "Missing inventory clip: " + path)
	var runner := load("res://runtime/lab/estate_animation_journey.gd") as GDScript
	assert(runner != null, "Journey runner must compile")
	await invalid_world_stop(runner)
	await physical_stop(runner)
	await restart_and_timeout(runner)
	if not journey_locomotion(): return
	if not await representative_door(): return
	if not await bed_handoff(): return
	print("PASS journey: complete inventory, ordered chapters, retained failure position, no advancing after failure, retry same chapter")
	quit(0)


func journey_locomotion() -> bool:
	var suite := preload("res://runtime/lab/estate_animation_journey.gd").new()
	root.add_child(suite)
	var actor: ElfieActor = suite.create_actor()
	root.add_child(actor)
	actor.configure("journey-locomotion-regression", Vector3.ZERO)
	actor.set_physics_process(false)
	actor.set_process(false)
	suite.set("_actor", actor)
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	suite.set("_player", player)
	actor.get("_animation_runtime").call("_install_animations", preload("res://runtime/lab/estate_animation_journey_plan.gd").clip_sources())
	suite.call("_install_navigation_locomotion")
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var hips := int(actor._furniture_hips()["bone"])
	for key: String in ["idle", "walking"]:
		player.play(key)
		player.advance(0.0)
		var first := skeleton.to_global(skeleton.get_bone_global_pose(hips).origin)
		var local_hips := skeleton.get_bone_pose_position(hips)
		var rest_hips := skeleton.get_bone_rest(hips).origin
		var rest_offset := skeleton.global_basis * (local_hips-rest_hips)
		if not check(rest_offset.length() < 0.03, "Journey locomotion lost the species rest height: offset=" + str(rest_offset)): return false
		for frame in range(61):
			player.seek(player.get_animation(key).length * float(frame) / 60.0, true)
			var point := skeleton.to_global(skeleton.get_bone_global_pose(hips).origin)
			if not check(Vector2(point.x-first.x, point.z-first.z).length() < 0.001, "Walking visual escaped the collision body"): return false
	actor.free()
	suite.free()
	print("PASS journey locomotion: confirmed rig height, in-place horizontal motion for full idle/walk cycles")
	return true


func representative_door() -> bool:
	var suite := DoorJourney.new()
	root.add_child(suite)
	var world := DoorWorld.new()
	suite.add_child(world)
	world.physics = DoorPhysics.new()
	world.add_child(world.physics)
	suite.set("_tour_world", world)
	var source := (load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene).instantiate() as Node3D
	world.add_child(source)
	for door: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var extra := door.get_meta("extras", {}) as Dictionary
		if not bool(extra.get("door_leaf", false)) or extra.get("connection") not in ["M01", "M02"]: continue
		door.reparent(world, true)
		world.physics._doors.append({"mesh": door})
		if extra.get("connection") == "M01": suite.get("_doors_seen")[door.get_instance_id()] = true
	source.free()
	if not check(await suite._internal_doors(), "Representative door must not require seven unrelated rooms"): return false
	if not check(suite.visited == ["dorm-01/bed-01", "central-01/activity"], "Door demo still repeats all eight rooms: " + str(suite.visited)): return false
	suite.get("_doors_seen").clear()
	if not check(not await suite._internal_doors(), "Representative door must actually open before the chapter succeeds"): return false
	suite.queue_free()
	await process_frame
	print("PASS representative door: one room round trip; other doors are not marked tested; unseen target door fails")
	return true


func restart_and_timeout(runner: GDScript) -> void:
	var nest := LoadingNest.new()
	root.add_child(nest)
	var suite: Node3D = runner.new()
	nest.add_child(suite)
	suite.set("load_timeout_seconds", 0.05)
	var characters := Node3D.new()
	nest.add_child(characters)
	await suite.setup(nest, characters)
	assert(bool(suite.get("_loading_failed")))
	assert(not bool(suite.get("_ready_for_play")))
	assert(str(suite.get("plan").blocked["reason"]).contains("timed out"))
	# Observe the restart request without actually replacing this test SceneTree.
	suite.runtime_restart_requested.disconnect(Callable(suite, "_restart_runtime"))
	var requests: Array[int] = [0]
	suite.runtime_restart_requested.connect(func() -> void: requests[0] += 1)
	suite.request_new_run()
	suite.request_new_run()
	assert(requests[0] == 1, "Repeated clicks must coalesce to one runtime restart")
	assert(bool(suite.get("_restart_pending")))
	nest.queue_free()
	await process_frame
	print("PASS new run: bounded loading failure, explicit restart request, repeated clicks do not stack scene loads")


func bed_handoff() -> bool:
	var room := preload("res://runtime/lab/chair_review_room.gd").new()
	root.add_child(room)
	var configured: Dictionary = await room.build()
	if not check(bool(configured["ready"]), "Actual M01 fixture navigation missing"): return false
	for frame in range(120):
		await physics_frame
		if NavigationServer3D.region_get_iteration_id(room.navigation.get_rid()) > 0: break
	await physics_frame
	await physics_frame
	var factory := preload("res://runtime/lab/chair_world_review.gd").new()
	var actor: ElfieActor = factory.create_actor()
	factory.free()
	actor.install_shared_animations = true
	room.add_child(actor)
	var marker: Marker3D = room.semantics.anchors["dorm-01/bed-01"]
	var floor_mesh: MeshInstance3D = room.semantics.room_floors["M01"]
	var centre := (floor_mesh.global_transform * floor_mesh.get_aabb()).get_center()
	centre.y = marker.global_position.y
	var start := Vector3.ZERO
	for frame in range(120):
		await process_frame
		start = NavigationServer3D.map_get_closest_point(room.get_world_3d().navigation_map, marker.global_position.move_toward(centre, 0.7))
		if not start.is_zero_approx(): break
	if not check(not start.is_zero_approx() and absf(start.y - marker.global_position.y) < 0.16, "Bed fixture floor navigation did not synchronize"): return false
	actor.configure("same-journey-test-dog", start)
	actor.set_physics_process(false)
	var before := actor.global_transform
	var duvet: MeshInstance3D
	for mesh: MeshInstance3D in room.geometry.find_children("*", "MeshInstance3D", true, false):
		var extra := mesh.get_meta("extras", {}) as Dictionary
		if extra.get("resident") == "A" and extra.get("piece") == "bed_cover": duvet = mesh
	var sleep := preload("res://runtime/lab/estate_sleep_journey.gd").new()
	room.add_child(sleep)
	var prepared: String = sleep.prepare(actor, marker, duvet, room.geometry, room.physics, "dorm-01/bed-01")
	if not check(prepared.is_empty(), "Sleep preparation: " + prepared): return false
	if not check(actor.global_transform.is_equal_approx(before), "Preparing poses moved the visible actor"): return false
	if not check(sleep.begin("back") == "bedside_not_physically_reached", "Unreached bed must reject contact"): return false
	var wall := sleep_wall(room, sleep.goal_position)
	await physics_frame
	var obstructed: String = sleep.validate_pose_path("back")
	if not check(obstructed.contains("sleep-test-wall"), "Foreign bed-entry obstacle was ignored: " + obstructed): return false
	wall.queue_free()
	await physics_frame
	await physics_frame
	actor.set_physics_process(true)
	Engine.time_scale = 4.0
	print("BED_ROUTE_INPUTS start=", actor.global_position, " goal=", sleep.goal_position, " nearest=", NavigationServer3D.map_get_closest_point(room.get_world_3d().navigation_map, sleep.goal_position), " region_iteration=", NavigationServer3D.region_get_iteration_id(room.navigation.get_rid()), " path=", NavigationServer3D.map_get_path(room.get_world_3d().navigation_map, actor.global_position, sleep.goal_position, true))
	if not check(actor.move_to("walk-to-real-bedside", sleep.goal_position, 12.0), "Bedside navigation was not accepted"): return false
	var reached: Array = await actor.navigation_terminal
	if not check(str(reached[1]) == "completed", "Bedside route blocked: " + str(reached)): return false
	actor.call("walk_precisely", sleep.goal_position, 8.0)
	var terminal: Signal = actor.get("precision_terminal")
	var docked: Array = await terminal
	if not check(bool(docked[0]), "Bedside precision walk failed"): return false
	await process_frame
	Engine.time_scale = 1.0
	for pose: String in ["back", "side-left", "side-right"]:
		var visual := actor.get_node("VisualRoot") as Node3D
		var visible_start := visual.global_transform
		var error: String = sleep.begin(pose)
		if not check(error.is_empty(), "Sleep contact " + pose + ": " + error): return false
		if not check(visual.global_transform.is_equal_approx(visible_start), "Bed contact teleported the visible actor"): return false
		if not check(actor.furniture_anchor_id == "dorm-01/bed-01", "Same actor did not own the real bed contact"): return false
		for frame in range(16): sleep.blend_entry(float(frame) / 15.0)
		for frame in range(151): sleep.sample(1.5 + 14.5 * float(frame) / 150.0)
		if pose == "back":
			wall = sleep_wall(room, sleep.goal_position)
			await physics_frame
			await process_frame
			if not check(sleep.finish().contains("sleep-test-wall") and sleep.active, "Blocked exit must retain the actual bed contact"): return false
			wall.queue_free()
			await physics_frame
			await process_frame
		sleep.effects.preview_cover(2.5)
		sleep.effects.preview_cover(6.0)
		var visible_exit := visual.global_transform
		var exit_error: String = sleep.finish()
		if not check(exit_error.is_empty(), "Real bed exit blocked: " + exit_error): return false
		if not check(visual.global_transform.is_equal_approx(visible_exit), "Leaving bed teleported the visible actor"): return false
		if not check(actor.furniture_anchor_id.is_empty() and actor.global_position.distance_to(sleep.goal_position) < 0.05, "Actor did not return to its physically reached bedside"): return false
		actor.get("_animation_runtime").advance(1.0)
		print("PASS continuous original duvet: ", pose, " same actor, real approach/contact, preserved visible entry and exit, no replacement cloth")
	room.queue_free()
	await process_frame
	await physics_frame
	return true


func sleep_wall(parent: Node3D, goal: Vector3) -> StaticBody3D:
	var wall := StaticBody3D.new()
	wall.set_meta("source_node", "sleep-test-wall")
	parent.add_child(wall)
	wall.global_position = goal + Vector3.UP * 0.7
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.8, 1.6, 0.8)
	collision.shape = shape
	wall.add_child(collision)
	return wall


func check(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok


func invalid_world_stop(runner: GDScript) -> void:
	var nest := UnreadyNest.new()
	nest._estate_physics = EmptyPhysics.new()
	nest.add_child(nest._estate_physics)
	root.add_child(nest)
	var characters := Node3D.new()
	nest.add_child(characters)
	var suite: Node3D = runner.new()
	nest.add_child(suite)
	await suite.setup(nest, characters)
	assert(not bool(suite.get("_ready_for_play")))
	assert(suite.get("_actor") == null)
	assert(str(suite.get("plan").blocked["reason"]).contains("precompiled collision"))
	print("PASS journey setup refuses stale/unloaded collision resources before creating a travelling actor")
	nest.queue_free()
	await process_frame


func physical_stop(runner: GDScript) -> void:
	# A real collision fixture exercises the arrival -> same body -> physical
	# step handoff. An obstacle must stop progress without changing its transform.
	var stage := Node3D.new()
	root.add_child(stage)
	var suite: Node3D = runner.new()
	stage.add_child(suite)
	suite.set_process(false)
	var actor: ElfieActor = suite.create_actor()
	stage.add_child(actor)
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	player.add_animation_library("", preload("res://runtime/actor/chair_clip_sequence.gd").locomotion_for(actor))
	var floor := MeshInstance3D.new()
	var surface := BoxMesh.new()
	surface.size = Vector3(8, 0.2, 8)
	floor.mesh = surface
	stage.add_child(floor)
	var body := StaticBody3D.new()
	stage.add_child(body)
	var shape := CollisionShape3D.new()
	shape.shape = surface.create_convex_shape()
	body.add_child(shape)
	var wall := StaticBody3D.new()
	wall.set_meta("source_node", "Journey test wall")
	stage.add_child(wall)
	wall.position = Vector3(0, 1, 0.9)
	var collision := CollisionShape3D.new()
	var block := BoxShape3D.new()
	block.size = Vector3(5, 2, 0.3)
	collision.shape = block
	wall.add_child(collision)
	var effects := preload("res://runtime/lab/estate_event_effects.gd").new()
	stage.add_child(effects)
	effects.configure_arrival(Vector3(0, 0.125, 0), 1.0)
	var cycle := preload("res://runtime/lab/estate_platform_cycle.gd").new()
	stage.add_child(cycle)
	var surfaces: Array[MeshInstance3D] = [floor]
	cycle.bind(effects, floor.get_aabb(), func(_seconds: float) -> void: pass, Vector3(0, 0.1, 3), surfaces, actor)
	assert(cycle.get("_body") == actor)
	assert(cycle.get_node_or_null("LocalPlatformBody") == null)
	cycle.sample(cycle.ARRIVAL_END)
	suite.set("_actor", actor)
	suite.set("_arrival", cycle)
	var start := actor.global_position
	Engine.time_scale = 6.0
	var accepted: bool = await suite.call("_execute_chapter", "platform-exit")
	Engine.time_scale = 1.0
	assert(not accepted, "Physical obstruction must fail the chapter")
	assert(actor.global_position.z < 0.8, "Actor crossed the real wall")
	assert(actor.global_position.distance_to(cycle.walk_profile.back()) > 1.0)
	assert(str(suite.get("_last_error")).contains("Journey test wall"))
	print("PASS physical journey stop: same arrival body, start=", start, " stopped=", actor.global_position, " reason=", suite.get("_last_error"))
	stage.queue_free()
	await process_frame
	await physics_frame
