extends SceneTree

const ACTOR_CONTROLLER_SCRIPT := preload("res://runtime/actor/actor_controller.gd")
const D := preload("res://rooms/room_dimensions.gd")
const MOCK_WANDER_CONTROLLER := preload("res://runtime/actor/mock_wander_controller.gd")
const MOCK_WANDER_TARGET := preload("res://runtime/actor/mock_wander_target.gd")
const WORLD_CONTROLLER_SCRIPT := preload("res://runtime/world/world_controller.gd")
const ACTOR_SCENES := {
	"dog": preload("res://characters/dog/dog.tscn"),
	"fox": preload("res://characters/fox/fox.tscn"),
}


func _init() -> void:
	call_deferred("run")


func run() -> void:
	var main_scene := load("res://main.tscn") as PackedScene
	var main := main_scene.instantiate()
	root.add_child(main)
	await process_frame
	var nest := main.get_node("Nest") as ModularNest
	_add_static_obstacle(nest)

	var world_controller := WORLD_CONTROLLER_SCRIPT.new()
	root.add_child(world_controller)
	world_controller.setup(nest)
	var configured: Dictionary = await world_controller.configure_world(
		{
			"nest_id": "mock-wander-whole-nest-test",
			"bed_count": 8,
			"world_revision": 1,
		},
		"configure-mock-wander-whole-nest",
	)
	if not _require(bool(configured.get("accepted", false)), "Whole Nest world failed to configure"):
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
	var sync_result := actor_controller.sync_actors([
		{
			"actor_id": "fox-1",
			"species": "fox",
			"spawn_anchor_id": "dorm-01/bed-01",
			"appearance": {},
		},
		{
			"actor_id": "dog-1",
			"species": "dog",
			"spawn_anchor_id": "dorm-01/bed-02",
			"appearance": {},
		},
	]) as Dictionary
	if not _require(bool(sync_result.get("accepted", false)), "Whole Nest actors failed to sync"):
		return
	await physics_frame

	var fox := actor_controller.actor("fox-1")
	var dog := actor_controller.actor("dog-1")
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
		waypoint_count >= 24,
		"Whole Nest Mock Wander did not expose all room-area waypoints",
	):
		return
	var regions: Dictionary = {}
	for waypoint in range(waypoint_count):
		var target: Variant = MOCK_WANDER_TARGET.target_for(nest, fox, waypoint, 1)
		if not _require(
			target is Vector3
				and MOCK_WANDER_TARGET.is_wanderable_position(nest, target as Vector3),
			"Whole Nest waypoint %d did not resolve to an allowed navigable target" % waypoint,
		):
			return
		regions[_region_key(target as Vector3)] = true
	if not _require(
		regions.has("activity-01")
			and regions.has("corridor")
			and regions.has("dorm-01")
			and regions.has("dorm-02"),
		"Whole Nest Mock Wander did not cover activity, corridor, and both dorm rooms",
	):
		return

	var wander: Variant = actor_controller.get("_mock_wander")
	if not _require(wander != null, "Whole Nest authority did not create Mock Wander"):
		return
	wander.set_process(false)
	wander._ensure_state("fox-1", Time.get_ticks_msec())
	wander._advance_actor(fox, Time.get_ticks_msec() + 60000)
	wander._ensure_state("dog-1", Time.get_ticks_msec())
	wander._advance_actor(dog, Time.get_ticks_msec() + 60000)
	if not _require(
		fox.active_command_id.begins_with("mock-wander-")
			and dog.active_command_id.begins_with("mock-wander-"),
		"Whole Nest Mock Wander did not start real actor navigation",
	):
		return

	var minimum_actor_distance := INF
	for _frame in range(2400):
		await physics_frame
		minimum_actor_distance = min(
			minimum_actor_distance,
			fox.global_position.distance_to(dog.global_position),
		)
		if fox.active_command_id.is_empty() and dog.active_command_id.is_empty():
			break
	if not _require(
		fox.active_command_id.is_empty() and dog.active_command_id.is_empty(),
		"Whole Nest Mock Wander did not complete its cross-area movements",
	):
		return
	if not _require(
		minimum_actor_distance >= 0.62,
		"Multiple Mock Wander actors violated collision clearance: %.3f" % minimum_actor_distance,
	):
		return

	var sleep_now := Time.get_ticks_msec()
	wander._sleep_actor(fox, sleep_now)
	wander._sleep_actor(dog, sleep_now)
	for _frame in range(2400):
		await physics_frame
		var fox_sleep_motion: Dictionary = wander.motion_for("fox-1")
		var dog_sleep_motion: Dictionary = wander.motion_for("dog-1")
		if (
			fox.active_command_id.is_empty()
			and dog.active_command_id.is_empty()
			and String(fox_sleep_motion.get("mode", "")) == "sleep"
			and String(dog_sleep_motion.get("mode", "")) == "sleep"
		):
			break
	var fox_bed := nest.resolve_anchor("dorm-01/bed-01")
	var dog_bed := nest.resolve_anchor("dorm-01/bed-02")
	if not _require(
		fox_bed != null
			and dog_bed != null
			and fox.global_position.distance_to(fox_bed.global_position) <= 0.5
			and dog.global_position.distance_to(dog_bed.global_position) <= 0.5
			and String(wander.motion_for("fox-1").get("mode", "")) == "sleep"
			and String(wander.motion_for("dog-1").get("mode", "")) == "sleep",
		"Whole Nest sleep schedule did not return each Elfie to its own bed",
	):
		return
	wander._wake_actor(fox, Time.get_ticks_msec())
	wander._wake_actor(dog, Time.get_ticks_msec())
	if not _require(
		wander.motion_for("fox-1").is_empty()
			and wander.motion_for("dog-1").is_empty(),
		"Whole Nest sleep schedule did not clear both sleep states at 06:00",
	):
		return

	var events: Array[Dictionary] = []
	actor_controller.runtime_event.connect(
		func(event_name: String, payload: Dictionary, _cause_id: String) -> void:
			events.append({"name": event_name, "payload": payload})
	)
	actor_controller.execute_intent({
		"command_id": "cross-room-obstacle",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "activity-02/activity",
		"deadline_seconds": 30.0,
	})
	for _frame in range(1800):
		await physics_frame
		if _terminal_for(events, "cross-room-obstacle") != null:
			break
	var terminal: Variant = _terminal_for(events, "cross-room-obstacle")
	if not _require(
		terminal != null
			and String(terminal.get("status", "")) == "completed",
		"Cross-room navigation did not route around the static obstacle: %s" % JSON.stringify(terminal),
	):
		return

	print("Whole Nest Mock Wander coverage, collision avoidance, and obstacle routing passed")
	quit(0)


func _add_static_obstacle(nest: ModularNest) -> void:
	var obstacle := StaticBody3D.new()
	obstacle.name = "WholeNestWanderTestObstacle"
	obstacle.position = Vector3(0.0, 0.9, -2.8)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(1.0, 1.8, 0.7)
	collision.shape = shape
	obstacle.add_child(collision)
	nest.add_child(obstacle)


func _region_key(position: Vector3) -> String:
	var room_index := clampi(int(floor(-position.z / D.CELL_PITCH)), 0, 7) + 1
	if position.x < D.ACTIVITY_INNER_X - 0.1:
		return "activity-%02d" % room_index
	if position.x > D.DORM_INNER_X + 0.1:
		return "dorm-%02d" % room_index
	return "corridor"


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
