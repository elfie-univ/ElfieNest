extends SceneTree

const WORLD := preload("res://runtime/world/world_controller.gd")
const ACTORS := preload("res://runtime/actor/actor_controller.gd")
const SPECIES := {"saevi": preload("res://characters/saevi/saevi.tscn"), "tovren": preload("res://characters/tovren/tovren.tscn")}
var _events: Array[Dictionary] = []
var _profile: FileAccess


func _init() -> void:
	call_deferred("run")


func run() -> void:
	_profile = FileAccess.open(ProjectSettings.globalize_path("res://../build/estate-runtime-profile.jsonl"), FileAccess.WRITE)
	var nest := (load("res://rooms/nest.tscn") as PackedScene).instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	await physics_frame
	for room in range(1, 9):
		for bed in range(1, 5):
			var id := "dorm-%02d/bed-%02d" % [room, bed]
			var marker := nest.resolve_anchor(id)
			if not check(marker != null, "Missing actual final-asset bed: " + id): return
			if not check(marker.has_meta("interaction_transform"), "Bed lacks physical sleeping pose: " + id): return
	var controller := WORLD.new()
	root.add_child(controller)
	controller.setup(nest)
	var configured: Dictionary = await controller.configure_world({"nest_id": "complete-estate-test", "bed_count": 32, "world_revision": 1}, "configure")
	if not bool(configured.get("accepted", false)):
		_diagnose_stairs(nest)
	if not check(bool(configured.get("accepted", false)), "Real complete estate navigation failed to configure"): return
	var map := nest.get_world_3d().navigation_map
	print("NAV_DIAGNOSTIC active=", NavigationServer3D.map_is_active(map), " regions=", NavigationServer3D.map_get_regions(map).size(), " iteration=", NavigationServer3D.map_get_iteration_id(map))
	var region := nest.get_node("RuntimeNavigation") as NavigationRegion3D
	print("NAV_REGION enabled=", region.enabled, " layers=", region.navigation_layers, " same_map=", region.get_navigation_map() == map, " vertices=", region.navigation_mesh.get_vertices().size())
	for id in nest.semantic_anchor_ids():
		var debug_marker := nest.resolve_anchor(id)
		if debug_marker == null: continue
		var debug_snap := NavigationServer3D.map_get_closest_point(map, debug_marker.global_position)
		if debug_snap.distance_to(debug_marker.global_position) >= 0.35:
			print("UNREACHABLE_APPROACH ", id, " point=", debug_marker.global_position, " snap=", debug_snap)
	var courtyard := nest.resolve_anchor("courtyard/activity")
	if not check(courtyard != null, "Courtyard has no real destination"): return
	for room in range(1, 9):
		for bed in range(1, 5):
			var marker := nest.resolve_anchor("dorm-%02d/bed-%02d" % [room, bed])
			var snap := NavigationServer3D.map_get_closest_point(map, marker.global_position)
			if not check(snap.distance_to(marker.global_position) < 0.35, "Bed approach is not on actual navigation: " + str(marker.name)): return
			var path := NavigationServer3D.map_get_path(map, marker.global_position, courtyard.global_position, true)
			if not check(path.size() >= 2 and path[-1].distance_to(courtyard.global_position) < 0.4, "Bed-to-courtyard route is disconnected: " + str(marker.name)): return
	print("PASS: 32 model-bound beds, real collision/navigation and every bedroom-to-courtyard route")
	_checkpoint("navigation_ready")
	var characters := Node3D.new()
	root.add_child(characters)
	var actors := ACTORS.new()
	root.add_child(actors)
	actors.setup(nest, characters, SPECIES, false)
	actors.runtime_event.connect(func(name: String, payload: Dictionary, _cause: String) -> void: _events.append({"name": name, "payload": payload}))
	var synced := actors.sync_actors([
		{"actor_id": "saevi-world", "species": "saevi", "spawn_anchor_id": "dorm-01/bed-01", "appearance": {"height_scale": 1.18, "build_scale": 1.15}},
		{"actor_id": "tovren-world", "species": "tovren", "spawn_anchor_id": "dorm-01/bed-02", "appearance": {}},
	])
	if not check(bool(synced.get("accepted", false)), "Real species could not spawn at real beds"): return
	var actor := actors.actor("saevi-world")
	var start := actor.global_position
	if OS.get_environment("ELFIENEST_ESTATE_STAIRS_ONLY") == "1":
		var target := OS.get_environment("ELFIENEST_ESTATE_STAIR_TARGET")
		if target.is_empty(): target = "terrace-01/activity"
		if not await _perform(actors, "stairs-only", "move_to_anchor", target): return
		if not check(actor.global_position.y > 3.0, "Maximum-size Actor did not physically ascend"): return
		_checkpoint("maximum_actor_physical_stairs")
		print("PASS: targeted maximum-size physical stairs to ", target)
		actors.queue_free()
		characters.queue_free()
		nest.queue_free()
		controller.queue_free()
		await process_frame
		quit(0)
		return
	if not await _perform(actors, "outdoor", "move_to_anchor", "courtyard/activity"): return
	if not check(actor.global_position.distance_to(start) > 5.0 and actor.furniture_anchor_id.is_empty(), "Move did not physically walk or secretly used furniture"): return
	print("PASS: real Actor walked bedroom -> automatic door -> courtyard")
	_checkpoint("real_actor_in_courtyard")
	if not await _perform(actors, "bed", "use_anchor", "dorm-01/bed-01"): return
	if not check(actor.runtime_posture() == "sleeping" and actor.furniture_anchor_id == "dorm-01/bed-01", "Actor did not really enter its bed pose"): return
	print("PASS: real Actor returned and used authored bed sleeping pose")
	_checkpoint("real_bed_used")
	var occupied := _command("occupied", "use_anchor", "dorm-01/bed-01", "tovren-world")
	actors.execute_intent(occupied)
	actors.execute_intent(occupied)
	if not _expect_terminal("occupied", "failed", "furniture_occupied"): return
	if not check(actor.runtime_posture() == "sleeping", "Occupied-bed rejection disturbed its real occupant"): return
	actors.execute_intent(_command("cancel-use", "use_anchor", "courtyard/lakeside-seat", "tovren-world"))
	actors.cancel_intent({"command_id": "cancel-use", "actor_id": "tovren-world"})
	if not _expect_terminal("cancel-use", "cancelled"): return
	if not check(actors.actor("tovren-world").furniture_anchor_id.is_empty(), "Cancelled action entered furniture"): return
	print("PASS: occupied furniture, command deduplication and cancellation retain one terminal")
	if not await _perform(actors, "chair", "use_anchor", "dorm-01/chair-01"): return
	if not check(actor.runtime_posture() == "sitting", "Actor did not sit in the authored chair"): return
	_checkpoint("real_chair_used")
	var stair_target := OS.get_environment("ELFIENEST_ESTATE_STAIR_TARGET")
	if stair_target.is_empty(): stair_target = "central-02/activity"
	if not check(stair_target in ["central-02/activity", "terrace-01/activity"], "Invalid stair test target"): return
	if not await _perform(actors, "upstairs", "move_to_anchor", stair_target): return
	if not check(actor.global_position.y > 3.0 and actor.furniture_anchor_id.is_empty(), "Actor did not physically climb to the actual upper floor"): return
	print("PASS: maximum-size Actor physically reached ", stair_target, " after real chair use and furniture exit")
	_checkpoint("real_actor_upstairs_" + stair_target)
	actors.queue_free()
	characters.queue_free()
	nest.queue_free()
	controller.queue_free()
	await process_frame
	quit(0)


func _perform(actors: Node, id: String, intent: String, target: String) -> bool:
	actors.execute_intent(_command(id, intent, target))
	for frame in range(14400):
		await physics_frame
		for event: Dictionary in _events:
			var payload: Dictionary = event["payload"]
			if event["name"] == "intent_terminal" and payload.get("command_id") == id:
				if str(payload.get("status")) != "completed":
					var failed_actor := actors.actor("saevi-world") as ElfieActor
					var contacts: Array = []
					for i in range(failed_actor.get_slide_collision_count()):
						var hit := failed_actor.get_slide_collision(i)
						contacts.append({"source": (hit.get_collider() as Node).get_meta("source_node", ""), "normal": str(hit.get_normal()), "point": str(hit.get_position())})
					print("ACTOR_FAILURE ", id, " event=", payload, " position=", failed_actor.global_position, " contacts=", contacts)
				return check(str(payload.get("status")) == "completed", "Actual action failed: " + id)
	return check(false, "Actual action timed out: " + id)


func _command(id: String, intent: String, target: String, actor_id: String = "saevi-world") -> Dictionary:
	return {"command_id": id, "intent_id": id, "actor_id": actor_id, "body_generation": 1, "initiator": "elfie", "intent": intent, "anchor_id": target, "deadline_seconds": 120.0}


func _expect_terminal(id: String, status: String, reason: String = "") -> bool:
	var terminals: Array[Dictionary] = []
	for event: Dictionary in _events:
		if event["name"] == "intent_terminal" and event["payload"].get("command_id") == id:
			terminals.append(event["payload"])
	return check(terminals.size() == 1 and terminals[0].get("status") == status and (reason.is_empty() or terminals[0].get("reason") == reason), "Expected one physical action terminal for %s, got %s" % [id, terminals])


func check(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok


func _checkpoint(stage: String) -> void:
	var output: Array = []
	OS.execute("/bin/ps", PackedStringArray(["-o", "rss=", "-p", str(OS.get_process_id())]), output)
	var entry := {"stage": stage, "rss_kib": str(output[0]).strip_edges().to_int() if not output.is_empty() else 0, "static_bytes": OS.get_static_memory_usage()}
	print("ESTATE_RUNTIME_PROFILE ", JSON.stringify(entry))
	if _profile != null:
		_profile.store_line(JSON.stringify(entry))
		_profile.flush()


func _diagnose_stairs(nest: ModularNest) -> void:
	var map := nest.get_world_3d().navigation_map
	for mesh: MeshInstance3D in nest.find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if extras.get("module") != "M01" or not str(extras.get("source_name", "")).begins_with("STAIR •"):
			continue
		var faces := mesh.mesh.get_faces()
		var levels := {}
		for i in range(0, faces.size(), 3):
			var a := mesh.global_transform * faces[i]
			var b := mesh.global_transform * faces[i + 1]
			var c := mesh.global_transform * faces[i + 2]
			var normal := (b - a).cross(c - a)
			if normal.length() < 0.00001 or absf(normal.normalized().y) < 0.99 or a.y < 0.4: continue
			var level := snappedf(a.y, 0.001)
			var area := normal.length()
			if not levels.has(level): levels[level] = {"sum": Vector3.ZERO, "area": 0.0}
			levels[level]["sum"] += (a + b + c) / 3.0 * area
			levels[level]["area"] += area
		for level: float in levels:
			var point: Vector3 = levels[level]["sum"] / float(levels[level]["area"])
			var hit := nest.get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(point + Vector3.UP * 0.03, point + Vector3.UP * 3.0))
			var clearance := -1.0 if hit.is_empty() else (hit["position"] as Vector3).y - point.y
			var source := "" if hit.is_empty() else str((hit["collider"] as Node).get_meta("source_node", ""))
			var to_ground := NavigationServer3D.map_get_path(map, point, nest.resolve_anchor("courtyard/activity").global_position, true)
			var to_terrace := NavigationServer3D.map_get_path(map, point, nest.resolve_anchor("terrace-01/activity").global_position, true)
			print("STAIR_CLEARANCE source=", mesh.name, " point=", point, " nav=", NavigationServer3D.map_get_closest_point(map, point), " headroom=", clearance, " above=", source, " ground_end=", to_ground[-1] if not to_ground.is_empty() else "none", " terrace_end=", to_terrace[-1] if not to_terrace.is_empty() else "none")
