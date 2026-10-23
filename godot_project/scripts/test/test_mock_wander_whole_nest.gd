extends SceneTree

const ACTOR_CONTROLLER_SCRIPT := preload("res://runtime/actor/actor_controller.gd")
const MOCK_WANDER_CONTROLLER := preload("res://runtime/actor/mock_wander_controller.gd")
const MOCK_WANDER_TARGET := preload("res://runtime/actor/mock_wander_target.gd")
const WORLD_CONTROLLER_SCRIPT := preload("res://runtime/world/world_controller.gd")
const ESTATE_PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const ACTOR_SCENES := {
	"tovren": preload("res://characters/tovren/tovren.tscn"),
	"saevi": preload("res://characters/saevi/saevi.tscn"),
}


func _init() -> void:
	call_deferred("run")


func run() -> void:
	var main_scene := load("res://main.tscn") as PackedScene
	var main := main_scene.instantiate()
	root.add_child(main)
	await process_frame
	var nest := main.get_node("Nest") as ModularNest

	var world_controller := WORLD_CONTROLLER_SCRIPT.new()
	root.add_child(world_controller)
	world_controller.setup(nest)
	var configured: Dictionary = await world_controller.configure_world(
		{
			"nest_id": "mock-wander-whole-nest-test",
			"bed_count": 32,
			"world_revision": 1,
		},
		"configure-mock-wander-whole-nest",
	)
	if not _require(bool(configured.get("accepted", false)), "Real whole-Nest navigation failed to configure: %s" % configured):
		return

	var actor_controller := ACTOR_CONTROLLER_SCRIPT.new()
	root.add_child(actor_controller)
	actor_controller.setup(
		nest,
		main.get_node("Characters") as Node3D,
		ACTOR_SCENES,
		false,
		true,
	)
	var wander: Variant = actor_controller.get("_mock_wander")
	if not _require(wander != null, "Whole Nest authority did not create Mock Wander"):
		return
	wander.set_process(false)
	var sync_result := actor_controller.sync_actors([
		{
			"actor_id": "saevi-1",
			"species": "saevi",
			"spawn_anchor_id": "dorm-01/bed-01",
			"appearance": {},
		},
		{
			"actor_id": "tovren-1",
			"species": "tovren",
			"spawn_anchor_id": "dorm-01/bed-02",
			"appearance": {},
		},
	]) as Dictionary
	if not _require(bool(sync_result.get("accepted", false)), "Whole Nest actors failed to sync"):
		return
	await physics_frame

	var saevi := actor_controller.actor("saevi-1")
	var tovren := actor_controller.actor("tovren-1")
	if not _require(
		not MOCK_WANDER_CONTROLLER.is_active_hour(5)
			and MOCK_WANDER_CONTROLLER.is_active_hour(6)
			and MOCK_WANDER_CONTROLLER.is_active_hour(23)
			and not MOCK_WANDER_CONTROLLER.is_active_hour(0),
		"Mock Wander daily schedule is not active from 06:00 through 23:59 only",
	):
		return
	var waypoint_count := MOCK_WANDER_TARGET.waypoint_count(nest)
	if not _require(
		waypoint_count == 6,
		"Whole Nest Mock Wander must preserve protocol waypoints 0..5",
	):
		return
	var regions: Dictionary = {}
	for room in range(1, 9):
		var home_id := "dorm-%02d/bed-01" % room
		saevi.set_meta("home_anchor_id", home_id)
		var expected_ids := [home_id, "dorm-%02d/door" % room, "central-01/activity",
			"courtyard/activity", "courtyard/lakeside-seat", "courtyard/picnic-seat"]
		for waypoint in range(waypoint_count):
			var target: Variant = MOCK_WANDER_TARGET.target_for(nest, saevi, waypoint, 1)
			var marker := nest.resolve_anchor(String(expected_ids[waypoint]))
			if not _require(
				target is Vector3 and marker != null
					and MOCK_WANDER_TARGET.is_wanderable_position(nest, target as Vector3)
					and (target as Vector3).distance_to(marker.global_position)
						<= MOCK_WANDER_TARGET.MAX_TARGET_SNAP_DISTANCE,
				"Room %d waypoint %d did not reach its real anchor" % [room, waypoint],
			):
				return
			regions[nest.nearest_zone_id(target as Vector3)] = true
	# Six route roles cannot enumerate every upper-floor zone. Check those actual
	# path endpoints separately, without changing the 0..5 payload contract.
	var map := nest.get_world_3d().navigation_map
	for level in range(2, 5):
		var marker := nest.resolve_anchor("central-%02d/activity" % level)
		if not _require(marker != null, "Real public floor anchor is missing"):
			return
		var path := NavigationServer3D.map_get_path(map, saevi.global_position, marker.global_position, true)
		if not _require(not path.is_empty()
			and path[path.size() - 1].distance_to(marker.global_position) <= 0.44,
			"Whole Nest public-floor path did not reach level %d" % level):
			return
		regions[nest.nearest_zone_id(marker.global_position)] = true
	saevi.remove_meta("home_anchor_id")
	for zone: Dictionary in nest.scene_manifest()["zones"]:
		if not bool(zone.get("active", false)) or String(zone.get("kind", "")) == "portal":
			continue
		if not _require(
			regions.has(String(zone["zone_id"])),
			"Whole Nest Mock Wander missed mapped zone %s" % zone["zone_id"],
		):
			return

	if not _require(MOCK_WANDER_TARGET.target_for(nest, saevi, -1) == null
		and MOCK_WANDER_TARGET.target_for(nest, saevi, 6) == null
		and MOCK_WANDER_TARGET.target_for(nest, null, 0) == null,
		"Invalid Mock route IDs or a missing actor did not fail closed"):
		return
	saevi.set_meta("home_anchor_id", "missing/bed")
	if not _require(MOCK_WANDER_TARGET.target_for(nest, saevi, 2) == null
		and MOCK_WANDER_TARGET.sleep_target(nest, saevi) == null,
		"Unknown home must not silently fall back to a guessed room"):
		return
	saevi.remove_meta("home_anchor_id")
	NavigationServer3D.map_set_active(map, false)
	await physics_frame
	var rejected_unready := (
		MOCK_WANDER_TARGET.target_for(nest, saevi, 3) == null
		and MOCK_WANDER_TARGET.sleep_target(nest, saevi) == null
		and not MOCK_WANDER_TARGET.is_wanderable_position(nest, saevi.global_position)
	)
	NavigationServer3D.map_set_active(map, true)
	for _frame in range(30):
		await physics_frame
		if MOCK_WANDER_TARGET.target_for(nest, saevi, 3) is Vector3:
			break
	if not _require(rejected_unready, "Inactive navigation map produced a guessed target"):
		return
	if not _require(MOCK_WANDER_TARGET.target_for(nest, saevi, 3) is Vector3,
		"Reactivated map did not restore a real reachable courtyard target"):
		return
	var motion_terminals := {}
	for moving_actor in [saevi, tovren]:
		moving_actor.navigation_terminal.connect(
			func(id: String, status: String, _reason: String) -> void:
				motion_terminals[id] = status
		)
	wander._ensure_state("saevi-1", Time.get_ticks_msec())
	wander._advance_actor(saevi, Time.get_ticks_msec() + 60000)
	wander._ensure_state("tovren-1", Time.get_ticks_msec())
	wander._advance_actor(tovren, Time.get_ticks_msec() + 60000)
	if not _require(
		saevi.active_command_id.begins_with("mock-wander-")
			and tovren.active_command_id.begins_with("mock-wander-"),
		"Whole Nest Mock Wander did not start real actor navigation",
	):
		return
	var saevi_move := saevi.active_command_id
	var tovren_move := tovren.active_command_id
	var saevi_motion: Dictionary = wander.motion_for("saevi-1")
	var tovren_motion: Dictionary = wander.motion_for("tovren-1")
	var saevi_target: Variant = MOCK_WANDER_TARGET.target_for(nest, saevi, int(saevi_motion["waypoint"]), int(saevi_motion["sequence"]))
	var tovren_target: Variant = MOCK_WANDER_TARGET.target_for(nest, tovren, int(tovren_motion["waypoint"]), int(tovren_motion["sequence"]))

	var minimum_actor_distance := INF
	for _frame in range(3600):
		await physics_frame
		minimum_actor_distance = min(
			minimum_actor_distance,
			saevi.global_position.distance_to(tovren.global_position),
		)
		if saevi.active_command_id.is_empty() and tovren.active_command_id.is_empty():
			break
	if not _require(
		saevi.active_command_id.is_empty() and tovren.active_command_id.is_empty()
			and motion_terminals.get(saevi_move) == "completed"
			and motion_terminals.get(tovren_move) == "completed"
			and saevi_target is Vector3 and tovren_target is Vector3
			and saevi.global_position.distance_to(saevi_target as Vector3) <= 0.44
			and tovren.global_position.distance_to(tovren_target as Vector3) <= 0.44,
		"Whole Nest Mock Wander stopped without physically completing its targets",
	):
		return
	if not _require(
		minimum_actor_distance >= 0.62,
		"Multiple Mock Wander actors violated collision clearance: %.3f" % minimum_actor_distance,
	):
		return

	var sleep_now := Time.get_ticks_msec()
	wander._sleep_actor(saevi, sleep_now)
	wander._sleep_actor(tovren, sleep_now)
	for _frame in range(3600):
		await physics_frame
		var saevi_sleep_motion: Dictionary = wander.motion_for("saevi-1")
		var tovren_sleep_motion: Dictionary = wander.motion_for("tovren-1")
		if (
			saevi.active_command_id.is_empty()
			and tovren.active_command_id.is_empty()
			and String(saevi_sleep_motion.get("mode", "")) == "sleep"
			and String(tovren_sleep_motion.get("mode", "")) == "sleep"
		):
			break
	var saevi_bed := nest.resolve_anchor("dorm-01/bed-01")
	var tovren_bed := nest.resolve_anchor("dorm-01/bed-02")
	if not _require(
		saevi_bed != null
			and tovren_bed != null
			and saevi.global_position.distance_to(saevi_bed.global_position) <= 0.5
			and tovren.global_position.distance_to(tovren_bed.global_position) <= 0.5
			and String(wander.motion_for("saevi-1").get("mode", "")) == "sleep"
			and String(wander.motion_for("tovren-1").get("mode", "")) == "sleep",
		"Whole Nest sleep schedule did not return each Elfie to its own bed",
	):
		return
	wander._wake_actor(saevi, Time.get_ticks_msec())
	wander._wake_actor(tovren, Time.get_ticks_msec())
	if not _require(
		wander.motion_for("saevi-1").is_empty()
			and wander.motion_for("tovren-1").is_empty(),
		"Whole Nest sleep schedule did not clear both sleep states at 06:00",
	):
		return

	var events: Array[Dictionary] = []
	actor_controller.runtime_event.connect(
		func(event_name: String, payload: Dictionary, _cause_id: String) -> void:
			events.append({"name": event_name, "payload": payload})
	)
	if not await _add_static_obstacle(nest):
		return
	actor_controller.execute_intent({
		"command_id": "cross-room-obstacle",
		"actor_id": "saevi-1",
		"intent": "move_to_anchor",
		"anchor_id": "courtyard/activity",
		"deadline_seconds": 60.0,
	})
	for _frame in range(3600):
		await physics_frame
		if _terminal_for(events, "cross-room-obstacle") != null:
			break
	var terminal: Variant = _terminal_for(events, "cross-room-obstacle")
	if not _require(
		terminal != null
			and String(terminal.get("status", "")) == "completed"
			and saevi.global_position.distance_to(nest.resolve_anchor("courtyard/activity").global_position) <= 0.44,
		"Cross-room navigation did not route around the static obstacle: %s" % JSON.stringify(terminal),
	):
		return

	print("Whole Nest Mock Wander coverage, collision avoidance, and obstacle routing passed")
	quit(0)


func _add_static_obstacle(nest: ModularNest) -> bool:
	var start := nest.resolve_anchor("dorm-01/bed-01")
	var target := nest.resolve_anchor("courtyard/activity")
	if not _require(start != null and target != null, "Obstacle route needs actual estate anchors"):
		return false
	var map := nest.get_world_3d().navigation_map
	var before := NavigationServer3D.map_get_path(map, start.global_position, target.global_position, true)
	var midpoint := Vector3.ZERO
	var direction := Vector3.ZERO
	for index in range(1, before.size()):
		var a := before[index - 1]
		var b := before[index]
		if a.distance_to(b) > 4.0 and absf(a.y - b.y) < 0.05:
			var point := (a + b) / 2.0
			if nest.nearest_zone_id(point) == "courtyard":
				midpoint = point
				direction = (b - a).normalized()
				break
	if not _require(not direction.is_zero_approx(), "No real courtyard path segment can host the routing obstacle"):
		return false
	var obstacle := StaticBody3D.new()
	obstacle.name = "WholeNestWanderTestObstacle"
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(1.0, 1.8, 0.7)
	collision.shape = shape
	obstacle.add_child(collision)
	nest.add_child(obstacle)
	obstacle.global_position = midpoint + Vector3.UP * 0.9
	obstacle.look_at(obstacle.global_position + direction, Vector3.UP)
	obstacle.add_to_group(ESTATE_PHYSICS.SOURCE_GROUP)
	await physics_frame
	var region := nest.get_node("RuntimeNavigation") as NavigationRegion3D
	var iteration := NavigationServer3D.map_get_iteration_id(map)
	region.bake_navigation_mesh(false)
	for _frame in range(60):
		await physics_frame
		if NavigationServer3D.map_get_iteration_id(map) > iteration:
			var after := NavigationServer3D.map_get_path(map, start.global_position, target.global_position, true)
			if after.is_empty() or after[after.size() - 1].distance_to(target.global_position) > 0.44:
				continue
			if _path_length(after) > _path_length(before) + 0.05:
				return true
	return _require(false, "Rebaked obstacle never produced a complete, physically longer detour")


func _path_length(path: PackedVector3Array) -> float:
	var result := 0.0
	for index in range(1, path.size()):
		result += path[index - 1].distance_to(path[index])
	return result

func _terminal_for(events: Array[Dictionary], command_id: String) -> Variant:
	for event in events:
		if (
			String(event.get("name", "")) == "intent_terminal"
			and String((event.get("payload", {}) as Dictionary).get("command_id", ""))
				== command_id
		):
			return event.get("payload", {})
	return null


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
