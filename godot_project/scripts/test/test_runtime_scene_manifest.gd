extends SceneTree

const BED_COUNTS := [32]
const WORLD_RUNTIME_CONTROLLER := preload("res://runtime/world/world_controller.gd")
const ESTATE_ASSERTIONS := preload("res://scripts/test/complete_estate_test_support.gd")

func _init() -> void:
	var nest_scene := load("res://rooms/nest.tscn") as PackedScene
	if nest_scene == null:
		push_error("Nest scene could not be loaded")
		quit(1)
		return
	var nest := nest_scene.instantiate() as ModularNest
	root.add_child(nest)
	await process_frame

	var revision := 1
	for requested_bed_count in BED_COUNTS:
		var result: Dictionary = nest.apply_world_config({
			"nest_id": "test-nest",
			"bed_count": requested_bed_count,
			"world_revision": revision,
		})
		if not bool(result.get("accepted", false)):
			push_error("Valid world config was rejected: %s" % [result])
			quit(1)
			return
		var manifest := result.get("manifest", {}) as Dictionary
		if not _assert_manifest(nest, manifest, requested_bed_count, revision):
			quit(1)
			return
		revision += 1

	var stable_before := JSON.stringify(nest.scene_manifest())
	var repeated: Dictionary = nest.apply_world_config({
		"nest_id": "test-nest",
		"bed_count": 32,
		"world_revision": revision - 1,
	})
	if not bool(repeated.get("accepted", false)):
		push_error("Repeated world config must be idempotent")
		quit(1)
		return
	if JSON.stringify(nest.scene_manifest()) != stable_before:
		push_error("Repeated world config changed the manifest")
		quit(1)
		return

	var stale: Dictionary = nest.apply_world_config({
		"nest_id": "test-nest",
		"bed_count": 32,
		"world_revision": revision - 2,
	})
	if bool(stale.get("accepted", true)) or String(stale.get("code", "")) != "stale_revision":
		push_error("Stale world revision was not rejected")
		quit(1)
		return
	if JSON.stringify(nest.scene_manifest()) != stable_before:
		push_error("Rejected config changed the world")
		quit(1)
		return

	var controller := WORLD_RUNTIME_CONTROLLER.new()
	root.add_child(controller)
	controller.setup(nest)
	var emitted_events: Array[String] = []
	controller.runtime_event.connect(
		func(event_name: String, _payload: Dictionary, _cause_id: String) -> void:
			emitted_events.append(event_name)
	)
	var ready_result: Dictionary = await controller.configure_world(
		{
			"nest_id": "test-nest",
			"bed_count": 32,
			"world_revision": revision,
		},
		"configure-final",
	)
	if (
		not bool(ready_result.get("accepted", false))
		or not controller.navigation_ready
	):
		push_error("Mapped complete estate did not become navigable: %s" % ready_result)
		quit(1)
		return
	if emitted_events != ["scene_manifest", "world_configured"]:
		push_error("World startup did not emit exactly one manifest and ready event")
		quit(1)
		return
	var map := nest.get_world_3d().navigation_map as RID
	var door := nest.resolve_anchor("dorm-01/door") as Marker3D
	if door == null or not NavigationServer3D.map_get_closest_point_owner(map, door.global_position).is_valid():
		push_error("Ready world has no navigation region bound to its real room door")
		quit(1)
		return

	var wire_config: Variant = JSON.parse_string(
		'{"nest_id":"wire-test","bed_count":32,"world_revision":%d}' % [revision + 1]
	)
	if not wire_config is Dictionary:
		push_error("JSON wire config did not decode to a dictionary")
		quit(1)
		return
	var wire_result := nest.apply_world_config(wire_config as Dictionary) as Dictionary
	if not bool(wire_result.get("accepted", false)):
		push_error("Valid JSON wire config was rejected: %s" % [wire_result])
		quit(1)
		return

	for invalid_bed_count in [0, 1, 3, 4, 31, 33]:
		var invalid := nest.apply_world_config({
			"nest_id": "test-nest",
			"bed_count": invalid_bed_count,
			"world_revision": revision + 2,
		}) as Dictionary
		if (
			bool(invalid.get("accepted", true))
			or String(invalid.get("code", "")) != "invalid_bed_count"
		):
			push_error("Out-of-range bed_count was not rejected")
			quit(1)
			return

	print("EVIDENCE_MANIFEST=%s" % JSON.stringify(nest.scene_manifest()))
	print("Runtime scene manifest contract passed")
	quit()


func _assert_manifest(
	nest: ModularNest,
	manifest: Dictionary,
	expected_bed_count: int,
	expected_revision: int,
) -> bool:
	if int(manifest.get("bed_count", 0)) != expected_bed_count:
		push_error("Manifest bed_count does not match requested bed_count")
		return false
	if int(manifest.get("world_revision", 0)) != expected_revision:
		push_error("Manifest revision does not match applied config revision")
		return false
	var error := ESTATE_ASSERTIONS.manifest_error(nest, manifest, expected_bed_count)
	if not error.is_empty():
		push_error(error)
		return false
	return true
