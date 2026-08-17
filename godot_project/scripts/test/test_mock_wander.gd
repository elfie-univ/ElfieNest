extends SceneTree

const ACTOR_CONTROLLER_SCRIPT := preload("res://runtime/actor/actor_controller.gd")
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
	var characters := main.get_node("Characters") as Node3D
	var world_controller := WORLD_CONTROLLER_SCRIPT.new()
	root.add_child(world_controller)
	world_controller.setup(nest)
	var configured: Dictionary = await world_controller.configure_world(
		{
			"nest_id": "mock-wander-test",
			"bed_count": 4,
			"world_revision": 1,
		},
		"configure-mock-wander",
	)
	if not _require(bool(configured.get("accepted", false)), "Mock Wander world failed to configure"):
		return

	var actor_controller := ACTOR_CONTROLLER_SCRIPT.new()
	root.add_child(actor_controller)
	actor_controller.setup(nest, characters, ACTOR_SCENES, false, true)
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
	if not _require(bool(sync_result.get("accepted", false)), "Mock Wander actors failed to sync"):
		return

	var events: Array[Dictionary] = []
	actor_controller.runtime_event.connect(
		func(event_name: String, payload: Dictionary, cause_id: String) -> void:
			events.append({"name": event_name, "payload": payload, "cause_id": cause_id})
	)
	await physics_frame
	var wander: Variant = actor_controller.get("_mock_wander")
	if not _require(wander != null, "Authority controller did not create Mock Wander"):
		return
	var system_hour := int(Time.get_time_dict_from_system().get("hour", 0))
	if not _require(
		wander._is_active_window() == (system_hour >= 8 and system_hour < 22),
		"Mock Wander active-window policy did not match its configured hours",
	):
		return
	# Drive one decision immediately so this contract test is independent of wall-clock hour.
	wander.set_process(false)
	var fox := actor_controller.actor("fox-1")
	var dog := actor_controller.actor("dog-1")
	wander._ensure_state("fox-1", Time.get_ticks_msec())
	wander._advance_actor(fox, Time.get_ticks_msec() + 60000)
	wander._ensure_state("dog-1", Time.get_ticks_msec())
	wander._advance_actor(dog, Time.get_ticks_msec() + 60000)
	var moving_snapshot := actor_controller.world_snapshot()
	var moving_actor := _actor_snapshot(moving_snapshot, "fox-1")
	var moving_dog := _actor_snapshot(moving_snapshot, "dog-1")
	var motion: Variant = moving_actor.get("mock_motion")
	if not _require(
		motion is Dictionary
			and int((motion as Dictionary).get("waypoint", -1)) >= 0
			and int((motion as Dictionary).get("sequence", 0)) == 1
			and fox.active_command_id.begins_with("mock-wander-"),
		"Authority did not expose one semantic Mock Wander waypoint while moving",
	):
		return
	var dog_motion: Variant = moving_dog.get("mock_motion")
	if not _require(
		dog_motion is Dictionary
			and int((dog_motion as Dictionary).get("waypoint", -1)) >= 0
			and int((dog_motion as Dictionary).get("sequence", 0)) == 1
			and dog.active_command_id.begins_with("mock-wander-"),
		"Authority did not schedule Mock Wander independently for the second actor",
	):
		return
	var target: Variant = MOCK_WANDER_TARGET.target_for(nest, fox, int((motion as Dictionary)["waypoint"]))
	if not _require(
		target is Vector3
			and nest.nearest_zone_id(target as Vector3) == "dorm-01",
		"Mock Wander target escaped its home zone or was not navigable",
	):
		return

	for _frame in range(600):
		await physics_frame
		if fox.active_command_id.is_empty() and dog.active_command_id.is_empty():
			break
	if not _require(
		fox.active_command_id.is_empty() and dog.active_command_id.is_empty(),
		"Mock Wander navigation did not reach its target",
	):
		return
	var resting_actor := _actor_snapshot(actor_controller.world_snapshot(), "fox-1")
	var resting_dog := _actor_snapshot(actor_controller.world_snapshot(), "dog-1")
	if not _require(
		not resting_actor.has("mock_motion")
			and not resting_dog.has("mock_motion")
			and not _has_event(events, "intent_terminal"),
		"Mock Wander leaked a fake intent terminal or stale motion after arrival",
	):
		return
	wander._advance_actor(fox, Time.get_ticks_msec() + 60000)
	var next_motion: Variant = _actor_snapshot(actor_controller.world_snapshot(), "fox-1").get("mock_motion")
	if not _require(
		next_motion is Dictionary
			and int((next_motion as Dictionary).get("sequence", 0)) == 2,
		"Mock Wander did not publish a new sequence after the rest interval",
	):
		return
	wander._stop_for_inactive_window(fox, Time.get_ticks_msec())
	if not _require(
		fox.active_command_id.is_empty()
			and not _actor_snapshot(actor_controller.world_snapshot(), "fox-1").has("mock_motion"),
		"Mock Wander inactive-window policy did not stop the temporary movement",
	):
		return

	var disabled_characters := Node3D.new()
	disabled_characters.name = "DisabledCharacters"
	root.add_child(disabled_characters)
	var disabled_controller := ACTOR_CONTROLLER_SCRIPT.new()
	root.add_child(disabled_controller)
	disabled_controller.setup(nest, disabled_characters, ACTOR_SCENES, false, false)
	var disabled_sync := disabled_controller.sync_actors([
		{
			"actor_id": "disabled-dog",
			"species": "dog",
			"spawn_anchor_id": "dorm-01/bed-03",
			"appearance": {},
		},
	]) as Dictionary
	if not _require(bool(disabled_sync.get("accepted", false)), "Disabled Mock Wander actor failed to sync"):
		return
	for _frame in range(4):
		await physics_frame
	var disabled_actor := disabled_controller.actor("disabled-dog")
	if not _require(
		disabled_actor != null
			and disabled_actor.active_command_id.is_empty()
			and not _actor_snapshot(disabled_controller.world_snapshot(), "disabled-dog").has("mock_motion"),
		"Mock Wander switch=false still moved an authority actor",
	):
		return

	print("Mock Wander authority movement, semantic replay state, and off switch passed")
	quit(0)


func _actor_snapshot(snapshot: Dictionary, actor_id: String) -> Dictionary:
	for raw_actor: Variant in snapshot.get("actors", []) as Array:
		var actor := raw_actor as Dictionary
		if actor != null and String(actor.get("actor_id", "")) == actor_id:
			return actor
	return {}


func _has_event(events: Array[Dictionary], event_name: String) -> bool:
	for event in events:
		if String(event.get("name", "")) == event_name:
			return true
	return false


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
