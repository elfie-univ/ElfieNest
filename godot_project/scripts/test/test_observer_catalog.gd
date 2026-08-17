extends SceneTree

const MAIN_SCRIPT := preload("res://main.gd")
const NEST_SCENE := preload("res://rooms/nest.tscn")
const OBSERVER_PRESENTATION := preload("res://runtime/observer/observer_presentation.gd")
const OBSERVER_BRIDGE := preload("res://runtime/observer/observer_bridge.gd")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const EXPECTED_INITIAL_VIEW_COUNT: int = 20


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	root.size = Vector2i(1280, 720)
	var instance := NEST_SCENE.instantiate()
	var nest := instance as ModularNest
	if not _require(nest != null, "Nest scene did not instantiate as ModularNest"):
		instance.free()
		return
	root.add_child(nest)
	await _wait_frames(4)

	var initial_catalog := nest.observer_camera_catalog()
	if not _require(
		_catalog_has_shape(initial_catalog),
		"Observer catalog exposes fields outside revision, views, active_id, and pause"
	):
		return
	if not _require(
		int(initial_catalog["revision"]) == 1
			and String(initial_catalog["active_id"]) == "overview",
		"Initial observer catalog revision or active id is not deterministic"
	):
		return
	var initial_views := initial_catalog["views"] as Array
	if not _require(
		initial_views.size() == EXPECTED_INITIAL_VIEW_COUNT
			and _view_matches(initial_views[0], "overview", "整体总览")
			and _view_matches(initial_views[1], "section-01", "区域俯视 01-04")
			and _view_matches(initial_views[2], "section-02", "区域俯视 05-08")
			and _view_matches(initial_views[3], "activity-01", "01 厨房")
			and _view_matches(initial_views[4], "dorm-01", "01 宿舍")
			and _view_matches(initial_views[initial_views.size() - 1], "portal", "传送室"),
		"Observer catalog ids and labels do not cover every generated view"
	):
		return

	if not _require(
		nest.select_observer_camera_by_id("activity-01")
			and String(nest.observer_camera_catalog()["active_id"]) == "activity-01",
		"Selecting a semantic observer view id did not activate it"
	):
		return
	var active_after_valid_select := String(nest.observer_camera_catalog()["active_id"])
	if not _require(
		not nest.select_observer_camera_by_id("missing-view")
			and String(nest.observer_camera_catalog()["active_id"])
				== active_after_valid_select,
		"Unknown observer view id changed active selection"
	):
		return
	nest.reset_observer_camera()
	await process_frame
	if not _require(
		String(nest.observer_camera_catalog()["active_id"]) == "activity-01",
		"Reset changed the selected observer view instead of resetting its camera"
	):
		return
	if not _require(
		nest.select_observer_overview()
			and String(nest.observer_camera_catalog()["active_id"]) == "overview",
		"Overview operation did not select the semantic overview id"
	):
		return

	nest.select_observer_camera_by_id("activity-01")
	nest.bed_count = 8
	await _wait_frames(4)
	var retained_catalog := nest.observer_camera_catalog()
	if not _require(
		int(retained_catalog["revision"]) > int(initial_catalog["revision"])
			and String(retained_catalog["active_id"]) == "activity-01",
		"Rebuild did not increment revision and retain an existing active id"
	):
		return
	nest.bed_count = 32
	await _wait_frames(4)
	if not _require(
		nest.select_observer_camera_by_id("section-01"),
		"Test setup could not select the section view before shrinking the layout"
	):
		return
	nest.bed_count = 5
	await _wait_frames(4)
	var fallback_catalog := nest.observer_camera_catalog()
	if not _require(
		int(fallback_catalog["revision"]) > int(retained_catalog["revision"])
			and String(fallback_catalog["active_id"]) == "overview"
			and _view_index_by_id(fallback_catalog["views"] as Array, "section-01") == -1,
		"Rebuild did not fall back to overview when the active id disappeared"
	):
		return

	var selected_camera := root.get_camera_3d()
	var size_before_pause := selected_camera.size
	nest.bed_count = 32
	await _wait_frames(4)
	if not _require(
		nest.select_observer_camera_by_id("section-01"),
		"Test setup could not select section-01 before paused rebuild"
	):
		return
	selected_camera = root.get_camera_3d()
	size_before_pause = selected_camera.size
	var active_id_before_pause := String(nest.observer_camera_catalog()["active_id"])
	nest.set_observer_presentation_paused(true)
	if not _require(
		not nest.select_observer_overview()
			and String(nest.observer_camera_catalog()["active_id"]) == active_id_before_pause,
		"Paused presentation accepted command-driven overview selection"
	):
		return
	if not _require(
		not nest.select_observer_camera_by_id("dorm-01")
			and String(nest.observer_camera_catalog()["active_id"]) == active_id_before_pause,
		"Paused presentation accepted command-driven semantic camera selection"
	):
		return
	nest.reset_observer_camera()
	await process_frame
	if not _require(
		String(nest.observer_camera_catalog()["active_id"]) == active_id_before_pause
			and is_equal_approx(selected_camera.size, size_before_pause),
			"Paused presentation accepted command-driven camera reset"
	):
		return
	nest.bed_count = 5
	await _wait_frames(4)
	var paused_rebuild_catalog := nest.observer_camera_catalog()
	if not _require(
		String(paused_rebuild_catalog["active_id"]) == "overview"
			and _view_index_by_id(paused_rebuild_catalog["views"] as Array, "section-01") == -1,
		"Paused presentation blocked internal rebuild active-view fallback"
	):
		return
	selected_camera = root.get_camera_3d()
	size_before_pause = selected_camera.size
	_send_wheel_up()
	await process_frame
	if not _require(
		nest.observer_presentation_paused()
			and is_equal_approx(selected_camera.size, size_before_pause),
		"Local presentation pause did not gate camera input"
	):
		return
	nest.set_observer_presentation_paused(false)
	_send_wheel_up()
	await process_frame
	if not _require(
		not nest.observer_presentation_paused()
			and selected_camera.size < size_before_pause,
		"Resuming local presentation did not restore camera input"
	):
		return

	var main := MAIN_SCRIPT.new()
	main._product_observer_mode = true
	main.nest = nest
	main._enter_product_observer_presentation_mode()
	if not _require(
		main.process_mode == Node.PROCESS_MODE_ALWAYS,
		"Product observer main does not keep polling while SceneTree is paused"
		):
		return
	var observer_bridge := OBSERVER_BRIDGE.new()
	observer_bridge.setup(nest, null, true)
	var valid_semantic_snapshot := {
		"channel": "elfienest.observer",
		"version": 1,
		"kind": "semantic_snapshot",
		"protocol": 3,
		"generation": 1,
		"sequence": 1,
		"scope": {"kind": "room", "room_id": "local-nest"},
		"entities": {
			"fox-1": {
				"room_id": "local-nest",
				"zone_id": "dorm-01",
				"posture": "standing",
				"active": true,
				"active_command_id": null,
				"species_id": "fox",
				"home_anchor_id": "dorm-01/bed-01",
				"appearance": {},
				"mock_motion": null,
			},
		},
		"entity_revisions": {"fox-1": 1},
	}
	if not _require(
		not (observer_bridge.call("_parse_semantic_snapshot", valid_semantic_snapshot) as Dictionary).is_empty(),
		"Semantic observer snapshot was not accepted"
	):
		return
	var coordinate_snapshot := valid_semantic_snapshot.duplicate(true)
	coordinate_snapshot["position"] = {"x": 1, "y": 2, "z": 3}
	if not _require(
		(observer_bridge.call("_parse_semantic_snapshot", coordinate_snapshot) as Dictionary).is_empty(),
		"Coordinate-bearing observer snapshot crossed the presentation boundary"
	):
		return
	var characters := Node3D.new()
	root.add_child(characters)
	var synthetic_visual_root := Node3D.new()
	root.add_child(synthetic_visual_root)
	var synthetic_mesh := MeshInstance3D.new()
	var synthetic_box := BoxMesh.new()
	synthetic_box.size = Vector3(1.0, 2.0, 1.0)
	synthetic_mesh.mesh = synthetic_box
	synthetic_mesh.position.y = 1.25
	synthetic_visual_root.add_child(synthetic_mesh)
	var synthetic_ground_offset := ACTOR_APPEARANCE.ground_visual_to_plane(
		synthetic_visual_root,
		0.0,
	)
	if not _require(
		is_equal_approx(synthetic_ground_offset, -0.25)
			and is_equal_approx(synthetic_visual_root.global_position.y, -0.25),
		"Visual grounding did not move a model whose lowest point was above the floor",
	):
		return
	synthetic_visual_root.queue_free()
	var presentation := OBSERVER_PRESENTATION.new()
	root.add_child(presentation)
	presentation.setup(nest, characters, {"fox": FOX_SCENE, "dog": DOG_SCENE})
	presentation.apply_snapshot(valid_semantic_snapshot)
	await _wait_frames(2)
	var grounded_actor := characters.get_child(0) as ElfieActor
	var grounded_visual_root := grounded_actor.get_node("VisualRoot") as Node3D
	var grounded_foot_y := float(
		ACTOR_APPEARANCE._foot_contact_y(grounded_visual_root)
	)
	if not _require(
		characters.get_child_count() == 1
			and grounded_actor.global_position
				== nest.resolve_anchor("dorm-01/bed-01").global_position
			and is_equal_approx(
				grounded_foot_y,
				nest.resolve_anchor("dorm-01/bed-01").global_position.y,
			),
		"Observer presentation did not place the Elfie at its semantic home anchor"
	):
		return
	var motion_snapshot := valid_semantic_snapshot.duplicate(true)
	(motion_snapshot["entities"]["fox-1"] as Dictionary)["mock_motion"] = {
		"waypoint": 1,
		"sequence": 1,
	}
	if not _require(nest.bake_navigation(), "Observer could not prepare its local replay NavMesh"):
		return
	for _frame in range(4):
		await physics_frame
	if not _require(
		not (observer_bridge.call("_parse_semantic_snapshot", motion_snapshot) as Dictionary).is_empty(),
		"Observer semantic snapshot rejected the temporary waypoint state",
	):
		return
	presentation.apply_snapshot(motion_snapshot)
	for _frame in range(4):
		await physics_frame
	if not _require(
		grounded_actor.active_command_id.begins_with("observer-mock-wander-"),
		"Observer did not replay the authority waypoint as local navigation",
	):
		return
	presentation.apply_snapshot(valid_semantic_snapshot)
	await _wait_frames(1)
	var multi_snapshot := valid_semantic_snapshot.duplicate(true)
	var dog_entity := (multi_snapshot["entities"]["fox-1"] as Dictionary).duplicate(true)
	dog_entity["species_id"] = "dog"
	dog_entity["home_anchor_id"] = "dorm-01/bed-02"
	(multi_snapshot["entities"] as Dictionary)["dog-1"] = dog_entity
	(multi_snapshot["entity_revisions"] as Dictionary)["dog-1"] = 1
	presentation.apply_snapshot(multi_snapshot)
	await _wait_frames(2)
	var dog_actor := characters.get_node_or_null("Dog") as ElfieActor
	var dog_visual_root := dog_actor.get_node("VisualRoot") as Node3D if dog_actor != null else null
	var dog_foot_y := float(
		ACTOR_APPEARANCE._foot_contact_y(dog_visual_root)
		if dog_visual_root != null
		else INF
	)
	if not _require(
		dog_actor != null
			and characters.get_child_count() == 2
			and dog_actor.global_position
				== nest.resolve_anchor("dorm-01/bed-02").global_position
			and is_equal_approx(
				dog_foot_y,
				nest.resolve_anchor("dorm-01/bed-02").global_position.y,
			),
		"Observer presentation did not ground both actors in a multi-Elfie snapshot",
	):
		return
	presentation.apply_snapshot(valid_semantic_snapshot)
	if not _require(
		characters.get_child_count() == 1,
		"Observer presentation recreated an unchanged actor"
	):
		return
	var empty_snapshot := valid_semantic_snapshot.duplicate(true)
	empty_snapshot["entities"] = {}
	empty_snapshot["entity_revisions"] = {}
	presentation.apply_snapshot(empty_snapshot)
	if not _require(
		characters.get_child_count() == 0,
		"Observer presentation did not remove a stale actor"
	):
		return
	var dynamic_room_snapshot := valid_semantic_snapshot.duplicate(true)
	(dynamic_room_snapshot["scope"] as Dictionary)["room_id"] = "room-42"
	(dynamic_room_snapshot["entities"]["fox-1"] as Dictionary)["room_id"] = "room-42"
	presentation.apply_snapshot(dynamic_room_snapshot)
	await _wait_frames(2)
	if not _require(
		characters.get_child_count() == 1,
		"Observer presentation rejected a valid non-default semantic room id"
	):
		return
	var world_config := {
		"channel": "elfienest.observer",
		"version": 1,
		"kind": "world_config",
		"nest_id": "local-nest",
		"bed_count": 4,
	}
	if not _require(
		not (observer_bridge.call("_parse_world_config", world_config) as Dictionary).is_empty(),
		"Strict observer world configuration was not accepted"
	):
		return
	if not _require(
		nest.apply_observer_world_config(world_config),
		"Observer world configuration was not applied to the Nest"
	):
		return
	await _wait_frames(4)
	var configured_catalog := nest.observer_camera_catalog()
	if not _require(
		nest.bed_count == 4
			and (configured_catalog["views"] as Array).size() == 4
			and _view_index_by_id(configured_catalog["views"] as Array, "dorm-01") >= 0
			and _view_index_by_id(configured_catalog["views"] as Array, "dorm-02") == -1
			and _view_index_by_id(configured_catalog["views"] as Array, "section-01") == -1
			and _view_index_by_id(configured_catalog["views"] as Array, "section-02") == -1,
		"Observer world configuration did not rebuild the four-bed geometry"
	):
		return
	var invalid_world_config := world_config.duplicate(true)
	invalid_world_config["bed_count"] = 33
	if not _require(
		(observer_bridge.call("_parse_world_config", invalid_world_config) as Dictionary).is_empty(),
		"Observer world configuration accepted an out-of-range bed count"
	):
		return
	nest.bed_count = 32
	await _wait_frames(4)
	selected_camera = root.get_camera_3d()
	size_before_pause = selected_camera.size
	if not _require(
		(observer_bridge.call("_parse_camera_command",
			_observer_command("select", {"view_id": "overview"})
		) as Dictionary).get("view_id") == "overview",
		"Typed observer select command was rejected"
	):
		return
	var browser_json_command: Variant = JSON.parse_string(JSON.stringify(
		_observer_command("select", {"view_id": "overview"})
	))
	if not _require(
		browser_json_command is Dictionary
			and (observer_bridge.call("_parse_camera_command", browser_json_command as Dictionary) as Dictionary)
				.get("view_id") == "overview",
		"Browser JSON select command was rejected after JSON.parse_string"
	):
		return
	for rejected_envelope in [
		_observer_command("overview", {}, true, "camera_command", "1"),
		_observer_command("overview", {}, true, "camera_command", 1.1),
		_observer_command("overview", {}, true, "camera_command", 0.999),
		_observer_command("overview", {}, true, "camera_command", 2.0),
		_observer_command(
			"overview",
			{},
			true,
			"camera_command",
			1,
			&"elfienest.observer",
		),
		_observer_command("overview", {}, true, &"camera_command"),
		_observer_command(&"overview"),
	]:
		if not _require(
			(observer_bridge.call("_parse_camera_command", rejected_envelope) as Dictionary).is_empty(),
			"Strict observer command envelope accepted a non-exact field type"
		):
			return
	for rejected in [
		_observer_command("reset", {}, false),
		_observer_command("next"),
		_observer_command("select"),
		_observer_command("select", {"view_id": ""}),
		_observer_command("select", {"view_id": 7}),
		_observer_command("select", {"view_id": "overview", "paused": false}),
		_observer_command("select", {"view_id": "overview", "x": 1}),
		_observer_command("select", {"view_id": "overview", "payload": {"x": 1, "y": 2}}),
		_observer_command("overview", {"simulation_pause": true}),
		_observer_command("overview", {"paused": true}),
		_observer_command("reset", {"view_id": "overview"}),
		_observer_command("reset", {}, true, "camera_catalog"),
		_observer_command("set_local_presentation_paused"),
		_observer_command("set_local_presentation_paused", {"paused": "true"}),
		_observer_command("set_local_presentation_paused", {"paused": true, "view_id": "overview"}),
	]:
		if not _require(
			(observer_bridge.call("_parse_camera_command", rejected) as Dictionary).is_empty(),
			"Malformed, open-shaped, nested, or coordinate-bearing command was accepted"
		):
			return

	observer_bridge.call("_handle_camera_command", {"action": "set_local_presentation_paused", "paused": true})
	var paused_bridge_active_id := String(nest.observer_camera_catalog()["active_id"])
	if not _require(
		nest.observer_presentation_paused()
			and main._runtime_client == null
			and main._world_controller == null
			and main._actor_controller == null
			and main._semantic_events == null,
		"Local presentation pause invoked authority transport state"
	):
		return
	observer_bridge.call("_handle_camera_command", {"action": "select", "view_id": "dorm-01"})
	if not _require(
		String(nest.observer_camera_catalog()["active_id"]) == paused_bridge_active_id,
		"Paused bridge command changed active view"
	):
		return
	observer_bridge.call("_handle_camera_command", {"action": "reset"})
	if not _require(
		String(nest.observer_camera_catalog()["active_id"]) == paused_bridge_active_id,
		"Paused bridge command reset changed active view"
	):
		return
	observer_bridge.call("_handle_camera_command", {"action": "set_local_presentation_paused", "paused": false})
	_send_wheel_up()
	await process_frame
	if not _require(
		not nest.observer_presentation_paused()
			and selected_camera.size < size_before_pause,
		"Continue command did not unlock local presentation input"
	):
		return
	main.free()
	print(
		"PASS: observer catalog ids, revisions, selection, reset, pause gating, and command parsing"
	)
	quit(0)


func _catalog_has_shape(catalog: Dictionary) -> bool:
	for key: Variant in catalog.keys():
		if String(key) not in ["revision", "views", "active_id", "presentation_paused"]:
			return false
	for raw_view: Variant in catalog.get("views", []):
		var view := raw_view as Dictionary
		if view == null or view.keys().size() != 2:
			return false
		if not view.has("id") or not view.has("label"):
			return false
	return true


func _view_matches(raw_view: Variant, view_id: String, label: String) -> bool:
	var view := raw_view as Dictionary
	if view == null:
		return false
	return String(view.get("id", "")) == view_id and String(view.get("label", "")) == label


func _view_index_by_id(views: Array, view_id: String) -> int:
	for index in range(views.size()):
		var view := views[index] as Dictionary
		if String(view.get("id", "")) == view_id:
			return index
	return -1


func _observer_command(
	action: Variant,
	fields: Dictionary = {},
	include_version: bool = true,
	kind: Variant = "camera_command",
	version: Variant = 1,
	channel: Variant = "elfienest.observer",
) -> Dictionary:
	var command := {
		"channel": channel,
		"kind": kind,
		"action": action,
	}
	if include_version:
		command["version"] = version
	for key: Variant in fields.keys():
		command[key] = fields[key]
	return command


func _send_wheel_up() -> void:
	var zoom := InputEventMouseButton.new()
	zoom.button_index = MOUSE_BUTTON_WHEEL_UP
	zoom.pressed = true
	Input.parse_input_event(zoom)


func _wait_frames(count: int) -> void:
	for frame in range(count):
		await process_frame


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
