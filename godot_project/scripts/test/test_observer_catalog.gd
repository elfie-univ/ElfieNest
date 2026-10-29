extends SceneTree

const MAIN_SCRIPT := preload("res://main.gd")
const NEST_SCENE := preload("res://rooms/nest.tscn")
const OBSERVER_PRESENTATION := preload("res://runtime/observer/observer_presentation.gd")
const OBSERVER_BRIDGE := preload("res://runtime/observer/observer_bridge.gd")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const SAEVI_SCENE := preload("res://characters/saevi/saevi.tscn")
const TOVREN_SCENE := preload("res://characters/tovren/tovren.tscn")
const EXPECTED_INITIAL_VIEW_COUNT: int = 21


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
			and _view_matches(initial_views[0], "overview", "庭院与建筑")
			and _view_matches(initial_views[1], "central-1", "主楼 · 1 层")
			and _view_matches(initial_views[4], "central-4", "主楼 · 4 层")
			and _view_matches(initial_views[5], "dorm-01", "宿舍 M01 · 一层")
			and _view_matches(initial_views[6], "terrace-01", "宿舍 M01 · 二层露台")
			and _view_matches(initial_views[20], "terrace-08", "宿舍 M08 · 二层露台"),
		"Observer catalog ids and labels do not cover every generated view"
	):
		return

	if not _require(
		nest.select_observer_camera_by_id("central-1")
			and String(nest.observer_camera_catalog()["active_id"]) == "central-1",
		"Selecting a semantic observer view id did not activate it"
	):
		return
	nest.select_observer_camera_by_id("dorm-01")
	var chair := nest.resolve_anchor("dorm-01/chair-01")
	var contact := (chair.get_meta("interaction_transform") as Transform3D).origin
	var dorm_camera := root.get_camera_3d()
	if not _require(
		not dorm_camera.is_position_behind(contact)
			and Rect2(Vector2.ZERO, Vector2(root.size)).has_point(dorm_camera.unproject_position(contact)),
		"Default dorm view hides the actual chair-01 contact",
	):
		return
	var sight := PhysicsRayQueryParameters3D.create(dorm_camera.global_position, contact + Vector3.UP * 0.6)
	if not _require(
		nest.get_world_3d().direct_space_state.intersect_ray(sight).is_empty(),
		"Default dorm camera is outside the shell or its view of the seated avatar is obstructed",
	):
		return
	nest.select_observer_camera_by_id("central-1")
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
		String(nest.observer_camera_catalog()["active_id"]) == "central-1",
		"Reset changed the selected observer view instead of resetting its camera"
	):
		return
	if not _require(
		nest.select_observer_overview()
			and String(nest.observer_camera_catalog()["active_id"]) == "overview",
		"Overview operation did not select the semantic overview id"
	):
		return

	nest.select_observer_camera_by_id("central-1")
	nest.bed_count = 32
	nest.rebuild()
	await _wait_frames(4)
	var retained_catalog := nest.observer_camera_catalog()
	if not _require(
		int(retained_catalog["revision"]) > int(initial_catalog["revision"])
			and String(retained_catalog["active_id"]) == "central-1",
		"Rebuild did not increment revision and retain an existing active id"
	):
		return
	nest.bed_count = 32
	await _wait_frames(4)
	if not _require(
		nest.select_observer_camera_by_id("overview"),
		"Test setup could not select the courtyard view before updating capacity"
	):
		return
	nest.bed_count = 32
	nest.set("_active_camera_id", "removed-view")
	nest.rebuild()
	await _wait_frames(4)
	var fallback_catalog := nest.observer_camera_catalog()
	if not _require(
		int(fallback_catalog["revision"]) > int(retained_catalog["revision"])
			and String(fallback_catalog["active_id"]) == "overview"
			and _view_index_by_id(fallback_catalog["views"] as Array, "removed-view") == -1,
		"Rebuild did not fall back to overview when the active id disappeared"
	):
		return

	var selected_camera := root.get_camera_3d()
	var size_before_pause := _camera_zoom(selected_camera)
	nest.bed_count = 32
	await _wait_frames(4)
	if not _require(
		nest.select_observer_camera_by_id("overview"),
		"Test setup could not select courtyard before paused rebuild"
	):
		return
	selected_camera = root.get_camera_3d()
	size_before_pause = _camera_zoom(selected_camera)
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
			and is_equal_approx(_camera_zoom(selected_camera), size_before_pause),
			"Paused presentation accepted command-driven camera reset"
	):
		return
	nest.bed_count = 32
	nest.rebuild()
	await _wait_frames(4)
	var paused_rebuild_catalog := nest.observer_camera_catalog()
	if not _require(
		String(paused_rebuild_catalog["active_id"]) == "overview"
			and _view_index_by_id(paused_rebuild_catalog["views"] as Array, "overview") >= 0,
		"Paused presentation lost its selected complete estate view during rebuild"
	):
		return
	selected_camera = root.get_camera_3d()
	size_before_pause = _camera_zoom(selected_camera)
	_send_wheel_up()
	await process_frame
	if not _require(
		nest.observer_presentation_paused()
			and is_equal_approx(_camera_zoom(selected_camera), size_before_pause),
		"Local presentation pause did not gate camera input"
	):
		return
	nest.set_observer_presentation_paused(false)
	_send_wheel_up()
	await process_frame
	if not _require(
		not nest.observer_presentation_paused()
			and _camera_zoom(selected_camera) < size_before_pause,
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
			"saevi-1": {
				"room_id": "local-nest",
				"zone_id": "dorm-01",
				"posture": "idle",
				"active": true,
				"active_command_id": null,
				"action_anchor_id": "dorm-01/bed-01",
				"species_id": "saevi",
				"home_anchor_id": "dorm-01/bed-01",
				"appearance": {},
				"mock_motion": null,
			},
		},
		"environment": null,
		"entity_revisions": {"saevi-1": 1},
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
	var world_config := {
		"channel": "elfienest.observer",
		"version": 1,
		"kind": "world_config",
		"nest_id": "local-nest",
		"bed_count": 32,
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
		nest.bed_count == 32
			and (configured_catalog["views"] as Array).size() == EXPECTED_INITIAL_VIEW_COUNT
			and _view_index_by_id(configured_catalog["views"] as Array, "dorm-01") >= 0
			and _view_index_by_id(configured_catalog["views"] as Array, "dorm-02") >= 0
			and _view_index_by_id(configured_catalog["views"] as Array, "overview") >= 0
			and _view_index_by_id(configured_catalog["views"] as Array, "section-02") == -1,
		"Observer world configuration changed the fixed complete estate camera layout"
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
	size_before_pause = _camera_zoom(selected_camera)
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
			and _camera_zoom(selected_camera) < size_before_pause,
		"Continue command did not unlock local presentation input"
	):
		return
	main.free()
	observer_bridge.free()
	print(
		"PASS: observer catalog ids, revisions, selection, reset, pause gating, and command parsing"
	)
	if not await _test_semantic_replay(nest, valid_semantic_snapshot):
		return
	quit(0)


func _test_semantic_replay(nest: ModularNest, valid_semantic_snapshot: Dictionary) -> bool:
	# Positive replay coverage remains strict until actual estate anchors and routes exist.
	if not _require(
		nest.resolve_anchor("dorm-01/bed-01") != null
			and nest.resolve_anchor("dorm-01/bed-02") != null
			and nest.bake_navigation(),
		"BLOCKED: complete estate semantic homes/navigation are not mapped; actor replay is unverified",
	):
		return false
	var observer_bridge := OBSERVER_BRIDGE.new()
	observer_bridge.setup(nest, null, true)
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
		return false
	synthetic_visual_root.queue_free()
	var presentation := OBSERVER_PRESENTATION.new()
	root.add_child(presentation)
	presentation.setup(nest, characters, {"saevi": SAEVI_SCENE, "tovren": TOVREN_SCENE})
	await presentation.prepare_navigation()
	_apply_replay(presentation, valid_semantic_snapshot)
	await _wait_frames(2)
	var grounded_actor := characters.get_child(0) as ElfieActor
	var grounded_visual_root := grounded_actor.get_node("VisualRoot") as Node3D
	var grounded_foot_y := float(
		ACTOR_APPEARANCE._foot_contact_y(grounded_visual_root)
	)
	print("Observer grounding: ready=%s actor=%s anchor=%s foot=%s error=%s" % [presentation.get("_navigation_ready"), grounded_actor.global_position, nest.resolve_anchor("dorm-01/bed-01").global_position, grounded_foot_y, grounded_actor.get_meta("observer_replay_error", "")])
	if not _require(
		characters.get_child_count() == 1
			and grounded_actor.global_position
				== nest.resolve_anchor("dorm-01/bed-01").global_position
			and absf(grounded_foot_y - nest.resolve_anchor("dorm-01/bed-01").global_position.y) <= 0.05,
		"Observer presentation did not place the Elfie at its semantic home anchor"
	):
		return false
	var motion_snapshot := valid_semantic_snapshot.duplicate(true)
	(motion_snapshot["entities"]["saevi-1"] as Dictionary)["action_anchor_id"] = null
	(motion_snapshot["entities"]["saevi-1"] as Dictionary)["mock_motion"] = {
		"waypoint": 1,
		"sequence": 1,
	}
	if not _require(nest.bake_navigation(), "Observer could not prepare its local replay NavMesh"):
		return false
	for _frame in range(4):
		await physics_frame
	if not _require(
		not (observer_bridge.call("_parse_semantic_snapshot", motion_snapshot) as Dictionary).is_empty(),
		"Observer semantic snapshot rejected the temporary waypoint state",
	):
		return false
	_apply_replay(presentation, motion_snapshot)
	for _frame in range(4):
		await physics_frame
	if not _require(
		grounded_actor.active_command_id.begins_with("observer-mock-wander-"),
		"Observer did not replay the authority waypoint as local navigation",
	):
		return false
	var whole_nest_motion_snapshot := valid_semantic_snapshot.duplicate(true)
	(whole_nest_motion_snapshot["entities"]["saevi-1"] as Dictionary)["action_anchor_id"] = null
	(whole_nest_motion_snapshot["entities"]["saevi-1"] as Dictionary)["mock_motion"] = {
		"waypoint": 23,
		"sequence": 3,
	}
	if not _require(
		not (observer_bridge.call("_parse_semantic_snapshot", whole_nest_motion_snapshot) as Dictionary).is_empty(),
		"Observer semantic snapshot rejected a whole-Nest waypoint beyond the legacy room range",
	):
		return false
	var sleep_snapshot := valid_semantic_snapshot.duplicate(true)
	(sleep_snapshot["entities"]["saevi-1"] as Dictionary)["action_anchor_id"] = null
	(sleep_snapshot["entities"]["saevi-1"] as Dictionary)["mock_motion"] = {
		"mode": "sleep",
		"sequence": 2,
	}
	if not _require(
		not (observer_bridge.call("_parse_semantic_snapshot", sleep_snapshot) as Dictionary).is_empty(),
		"Observer semantic snapshot rejected the sleep-return motion state",
	):
		return false
	_apply_replay(presentation, valid_semantic_snapshot)
	await _wait_frames(1)
	_apply_replay(presentation, sleep_snapshot)
	for _frame in range(600):
		await physics_frame
		if (
			grounded_actor.active_command_id.is_empty()
			and grounded_actor.global_position.distance_to(
				nest.resolve_anchor("dorm-01/bed-01").global_position
			) <= 0.5
		):
			break
	if not _require(
		grounded_actor.global_position.distance_to(
			nest.resolve_anchor("dorm-01/bed-01").global_position
		) <= 0.5,
		"Observer did not replay sleep motion back to the semantic home bed",
	):
		return false
	_apply_replay(presentation, valid_semantic_snapshot)
	await _wait_frames(1)
	var multi_snapshot := valid_semantic_snapshot.duplicate(true)
	var tovren_entity := (multi_snapshot["entities"]["saevi-1"] as Dictionary).duplicate(true)
	tovren_entity["species_id"] = "tovren"
	tovren_entity["home_anchor_id"] = "dorm-01/bed-02"
	tovren_entity["action_anchor_id"] = "dorm-01/bed-02"
	(multi_snapshot["entities"] as Dictionary)["tovren-1"] = tovren_entity
	(multi_snapshot["entity_revisions"] as Dictionary)["tovren-1"] = 1
	_apply_replay(presentation, multi_snapshot)
	await _wait_frames(2)
	var tovren_actor := characters.get_node_or_null("Tovren") as ElfieActor
	var tovren_visual_root := tovren_actor.get_node("VisualRoot") as Node3D if tovren_actor != null else null
	var tovren_foot_y := float(
		ACTOR_APPEARANCE._foot_contact_y(tovren_visual_root)
		if tovren_visual_root != null
		else INF
	)
	if not _require(
		tovren_actor != null
			and characters.get_child_count() == 2
			and tovren_actor.global_position
				== nest.resolve_anchor("dorm-01/bed-02").global_position
			and absf(tovren_foot_y - nest.resolve_anchor("dorm-01/bed-02").global_position.y) <= 0.05,
		"Observer presentation did not ground both actors in a multi-Elfie snapshot",
	):
		return false
	_apply_replay(presentation, valid_semantic_snapshot)
	if not _require(
		characters.get_child_count() == 1,
		"Observer presentation recreated an unchanged actor"
	):
		return false
	var empty_snapshot := valid_semantic_snapshot.duplicate(true)
	empty_snapshot["entities"] = {}
	empty_snapshot["entity_revisions"] = {}
	_apply_replay(presentation, empty_snapshot)
	if not _require(
		characters.get_child_count() == 0,
		"Observer presentation did not remove a stale actor"
	):
		return false
	var dynamic_room_snapshot := valid_semantic_snapshot.duplicate(true)
	(dynamic_room_snapshot["scope"] as Dictionary)["room_id"] = "room-42"
	(dynamic_room_snapshot["entities"]["saevi-1"] as Dictionary)["room_id"] = "room-42"
	_apply_replay(presentation, dynamic_room_snapshot)
	await _wait_frames(2)
	if not _require(
		characters.get_child_count() == 1,
		"Observer presentation rejected a valid non-default semantic room id"
	):
		return false
	observer_bridge.free()
	return true


func _apply_replay(presentation: Node, snapshot: Dictionary) -> void:
	var current := int(presentation.get("_snapshot_sequence"))
	var next := snapshot.duplicate(true)
	next["sequence"] = current + 1
	presentation.apply_snapshot(next)


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


func _camera_zoom(camera: Camera3D) -> float:
	return camera.fov if camera.projection == Camera3D.PROJECTION_PERSPECTIVE else camera.size


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
