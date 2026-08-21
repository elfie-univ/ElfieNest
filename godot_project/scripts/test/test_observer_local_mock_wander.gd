extends SceneTree

const MOCK_WANDER_TARGET := preload("res://runtime/actor/mock_wander_target.gd")
const OBSERVER_PRESENTATION := preload("res://runtime/observer/observer_presentation.gd")
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
			"nest_id": "observer-local-mock-test",
			"bed_count": 8,
			"world_revision": 1,
		},
		"configure-observer-local-mock",
	)
	if not _require(bool(configured.get("accepted", false)), "Observer test world failed to configure"):
		return
	if not _require(nest.bake_navigation(), "Observer test could not prepare its local NavMesh"):
		return
	for _frame in range(4):
		await physics_frame

	var presentation := OBSERVER_PRESENTATION.new()
	root.add_child(presentation)
	presentation.setup(nest, characters, ACTOR_SCENES, true)
	presentation.apply_snapshot({
		"entities": {
			"fox-1": {
				"room_id": "local-nest",
				"zone_id": "dorm-01",
				"posture": "standing",
				"active": true,
				"active_command_id": null,
				"species_id": "fox",
				"appearance": {},
				"home_anchor_id": "dorm-01/bed-01",
				"mock_motion": null,
			},
		},
	})
	await process_frame
	await physics_frame

	var actor := characters.get_child(0) as ElfieActor
	if not _require(actor != null, "Observer local Mock did not create an actor"):
		return
	var states := presentation.get("_local_mock_states") as Dictionary
	var state := states["fox-1"] as Dictionary
	state["phase"] = "resting"
	state["next_at_msec"] = Time.get_ticks_msec() - 1
	states["fox-1"] = state
	presentation.call(
		"_advance_local_mock_actor",
		actor,
		Time.get_ticks_msec() + 60000,
	)

	if not _require(
		actor.active_command_id.begins_with("observer-local-mock-wander-"),
		"Observer local Mock did not start local navigation",
	):
		return
	var local_state := (presentation.get("_local_mock_states") as Dictionary)["fox-1"] as Dictionary
	var waypoint := int(local_state["waypoint"])
	if not _require(
		waypoint >= 0 and waypoint < MOCK_WANDER_TARGET.waypoint_count(nest),
		"Observer local Mock selected a waypoint outside the whole Nest",
	):
		return
	if not _require(
		not actor.active_command_id.begins_with("observer-mock-wander-"),
		"Observer local Mock unexpectedly used the authority replay command",
	):
		return

	print("Observer local whole-Nest Mock Wander passed")
	quit(0)


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	printerr(message)
	quit(1)
	return false
