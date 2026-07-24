extends SceneTree

const BED_COUNTS := [1, 4, 5, 16, 32]
const WORLD_RUNTIME_CONTROLLER := preload("res://runtime/world_controller.gd")

func _init() -> void:
	var nest_scene := load("res://rooms/nest.tscn") as PackedScene
	if nest_scene == null:
		push_error("Nest scene could not be loaded")
		quit(1)
		return
	var nest := nest_scene.instantiate()
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
		if requested_bed_count == 5:
			print("EVIDENCE_FIVE_BEDS=%s" % JSON.stringify(manifest))
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
		"bed_count": 4,
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
		func(event_name: String, _payload: Dictionary, _correlation_id: String) -> void:
			emitted_events.append(event_name)
	)
	var ready_result: Dictionary = await controller.configure_world(
		{
			"nest_id": "test-nest",
			"bed_count": 4,
			"world_revision": revision,
		},
		"configure-final",
	)
	if not bool(ready_result.get("accepted", false)):
		push_error("World controller rejected a valid final config")
		quit(1)
		return
	if emitted_events != ["scene_manifest", "world_ready"]:
		push_error("world_ready must follow scene_manifest exactly once")
		quit(1)
		return
	if not controller.navigation_ready:
		push_error("world_ready emitted before navigation preparation")
		quit(1)
		return

	var wire_config: Variant = JSON.parse_string(
		'{"nest_id":"wire-test","bed_count":4,"world_revision":%d}' % [revision + 1]
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

	for invalid_bed_count in [0, 33]:
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
	nest: Node,
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
	var anchors := manifest.get("anchors", []) as Array
	var bed_anchor_ids: Array[String] = []
	for anchor in anchors:
		if not anchor is Dictionary:
			continue
		var anchor_dict := anchor as Dictionary
		if anchor_dict.has("position") or anchor_dict.has("node_path"):
			push_error("Manifest anchors must not export engine coordinates or paths")
			return false
		if not anchor_dict.has("active"):
			push_error("Manifest anchor is missing active state")
			return false
		if String(anchor_dict.get("kind", "")) == "bed":
			var anchor_id := String(anchor_dict.get("anchor_id", ""))
			bed_anchor_ids.append(anchor_id)
			if nest.resolve_anchor(anchor_id) == null:
				push_error("Bed semantic ID does not resolve to Marker3D")
				return false
	if bed_anchor_ids.size() != expected_bed_count:
		push_error("Manifest bed anchor count does not match requested bed_count")
		return false
	var sorted_ids := bed_anchor_ids.duplicate()
	sorted_ids.sort()
	if sorted_ids != bed_anchor_ids:
		push_error("Bed anchors do not have stable semantic ordering")
		return false
	return true
