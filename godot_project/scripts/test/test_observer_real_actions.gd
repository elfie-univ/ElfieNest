extends SceneTree

## Focused replay fixture: real Saevi locomotion/poses, no complete estate or transport.
const BRIDGE := preload("res://runtime/observer/observer_bridge.gd")
const PRESENTATION := preload("res://runtime/observer/observer_presentation.gd")
const SAEVI := preload("res://characters/saevi/saevi.tscn")

class ReplayNest extends ModularNest:

	var markers: Dictionary = {}

	func _ready() -> void:
		pass

	func resolve_anchor(anchor_id: String) -> Marker3D:
		return markers.get(anchor_id) as Marker3D

	func semantic_anchor_ids() -> Array[String]:
		var ids: Array[String] = []
		for id: String in markers:
			ids.append(id)
		return ids

	func bake_navigation() -> bool:
		return get_node_or_null("ReplayNavigation") != null

	func validate_navigation_anchors() -> bool:
		return true


var _errors: Array[String] = []
var _sequence := 0


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var nest := ReplayNest.new()
	var hud: Node = load("res://ui/observation_hud.tscn").instantiate()
	hud.name = "ObservationHUD"
	nest.add_child(hud)
	root.add_child(nest)
	_add_navigation(nest)
	var bed := _marker(nest, "dorm-01/bed-01", "bed", Vector3(-3, 0.02, 0), "sleeping")
	var chair := _marker(nest, "dorm-01/chair-01", "chair", Vector3(0, 0.02, 2), "sitting")
	var activity := _marker(nest, "courtyard/activity", "activity", Vector3(3, 0.02, 0))
	var invalid := _marker(nest, "dorm-01/chair-02", "chair", Vector3(0, 0.02, -2))
	var characters := Node3D.new()
	# Reproduce the product main's ALWAYS ancestry, not just a pausable test root.
	characters.process_mode = Node.PROCESS_MODE_ALWAYS
	root.add_child(characters)
	var presentation := PRESENTATION.new()
	root.add_child(presentation)
	presentation.setup(nest, characters, {"saevi": SAEVI})
	var bridge := BRIDGE.new()
	root.add_child(bridge)
	bridge.setup(nest, presentation, true)
	var initial := _snapshot("idle", null, null)
	_check(not (bridge._parse_semantic_snapshot(initial)).is_empty(), "nullable action anchor rejected")
	for bad_value: Variant in [7, false, {}, [], ""]:
		var malformed := initial.duplicate(true)
		malformed["entities"]["saevi-1"]["action_anchor_id"] = bad_value
		_check(bridge._parse_semantic_snapshot(malformed).is_empty(), "invalid action anchor type accepted")
	for mutation: String in ["missing", "extra", "coordinates"]:
		var malformed := initial.duplicate(true)
		var entity := malformed["entities"]["saevi-1"] as Dictionary
		if mutation == "missing":
			entity.erase("action_anchor_id")
		elif mutation == "extra":
			entity["target"] = "courtyard/activity"
		else:
			entity["appearance"] = {"position": {"x": 1}}
		_check(bridge._parse_semantic_snapshot(malformed).is_empty(), "non-exact entity accepted: " + mutation)
	bridge._handle_semantic_snapshot(initial)
	var actor := characters.get_child(0) as ElfieActor
	_check(actor.install_shared_animations, "real avatar shared animations disabled")
	_check(actor.process_mode == Node.PROCESS_MODE_PAUSABLE, "display actor inherited ALWAYS processing")
	var navigation_agent := actor.get_node("NavigationAgent3D") as NavigationAgent3D
	_check(navigation_agent.process_mode == Node.PROCESS_MODE_INHERIT, "navigation agent no longer inherits display pause")
	var walk := _snapshot("walking", "walk-1", "courtyard/activity")
	bridge._handle_semantic_snapshot(walk)
	_check(actor.active_command_id.is_empty(), "walk began before local navigation sync")
	for _frame in range(90):
		await physics_frame
		if not actor.active_command_id.is_empty():
			break
	_check(not actor.active_command_id.is_empty(), "pending walk never started after navigation sync")
	await process_frame
	_check(nest.observer_camera_catalog()["active_id"] == "elfie-saevi-1", "first visible resident was not framed")
	var command := actor.active_command_id
	var deadline := int(actor.get("_deadline_msec"))
	bridge._handle_semantic_snapshot(walk)
	var duplicate := _snapshot("walking", "walk-1", "courtyard/activity")
	bridge._handle_semantic_snapshot(duplicate)
	_check(actor.active_command_id == command and int(actor.get("_deadline_msec")) == deadline, "duplicate restarted walk")
	var origin := actor.global_position
	for _frame in range(12):
		await physics_frame
	_check(actor.global_position.distance_to(origin) > 0.05 and actor.active_command_id == command, "mid-walk pause fixture was not moving")
	bridge._handle_camera_command({"action": "set_local_presentation_paused", "paused": true})
	var mid_walk_position := actor.global_position
	for _frame in range(12):
		await physics_frame
		_check(actor.global_position.is_equal_approx(mid_walk_position), "paused display actor continued physical navigation")
	_check(actor.active_command_id == command, "pause cancelled the local walk")
	bridge._handle_camera_command({"action": "set_local_presentation_paused", "paused": false})
	for _frame in range(12):
		await physics_frame
	_check(actor.global_position.distance_to(mid_walk_position) > 0.05, "resumed display actor did not continue walking")
	for _frame in range(480):
		await physics_frame
		if actor.active_command_id.is_empty():
			break
	_check(actor.global_position.distance_to(activity.global_position) <= ElfieActor.ARRIVAL_DISTANCE * 2.0, "real local walk failed")
	_check(actor.furniture_anchor_id.is_empty(), "walking automatically used furniture")
	bridge._handle_semantic_snapshot(_snapshot("idle", null, "courtyard/activity"))
	_check(actor.global_position.distance_to(activity.global_position) < 0.44, "completed arrival was not reached")
	for _frame in range(2):
		await process_frame
	var appearance := load("res://runtime/actor/actor_appearance.gd")
	_check(absf(float(appearance._foot_contact_y(actor.get_node("VisualRoot"))) - activity.global_position.y) <= 0.05, "animated avatar feet sank below its standing origin")
	var retained := actor.get_instance_id()
	var before_arrival := actor.global_position
	bridge._handle_semantic_snapshot(_snapshot("idle", null, "dorm-01/bed-01"))
	_check(actor.global_position.is_equal_approx(before_arrival), "terminal snapshot teleported the avatar across the room")
	await _wait_arrival(actor)
	_check(actor.furniture_anchor_id.is_empty() and actor.runtime_posture() == "idle", "arrival at bed automatically used it")
	var sleep := _snapshot("sleeping", null, "dorm-01/bed-01")
	bridge._handle_semantic_snapshot(sleep)
	await _wait_arrival(actor)
	_check(actor.runtime_posture() == "sleeping" and actor.furniture_anchor_id == "dorm-01/bed-01", "authored bed pose missing")
	_check_contact(actor, bed)
	var visual := actor.get_node("VisualRoot") as Node3D
	var sleep_transform := visual.transform
	bridge._handle_semantic_snapshot(_snapshot("sleeping", null, "dorm-01/bed-01"))
	_check(visual.transform.is_equal_approx(sleep_transform), "duplicate accumulated bed pose")
	bridge._handle_semantic_snapshot(_snapshot("sitting", null, "dorm-01/chair-01"))
	await _wait_arrival(actor)
	_check(actor.runtime_posture() == "sitting" and actor.furniture_anchor_id == "dorm-01/chair-01", "authored chair pose missing")
	_check_contact(actor, chair)
	bridge._handle_semantic_snapshot(_snapshot("sitting", null, "dorm-01/chair-02"))
	_check(actor.furniture_anchor_id.is_empty(), "invalid furniture metadata retained old pose")
	_check(String(actor.get_meta("observer_replay_error", "")).length() > 0, "invalid pose was silently accepted")
	_check(not invalid.has_meta("interaction_transform"), "test accidentally supplied a valid pose")
	bridge._handle_semantic_snapshot(_snapshot("walking", "walk-2", "dorm-01/bed-01"))
	_check(actor.furniture_anchor_id.is_empty(), "departure retained furniture pose")
	bridge._handle_semantic_snapshot(_snapshot("idle", null, null))
	var cancelled_position := actor.global_position
	_check(actor.active_command_id.is_empty(), "unknown cancellation kept replay moving")
	var unknown := _snapshot("walking", "unknown-target", "missing/anchor")
	unknown["entities"]["saevi-1"]["mock_motion"] = {"mode": "sleep", "sequence": 1}
	bridge._handle_semantic_snapshot(unknown)
	_check(actor.active_command_id.is_empty() and actor.global_position == cancelled_position, "unknown anchor invented a home action")
	bridge._handle_semantic_snapshot(walk)
	_check(actor.active_command_id.is_empty(), "stale snapshot restarted walk")
	_check(actor.get_instance_id() == retained, "semantic actions recreated the avatar")
	bridge._handle_semantic_snapshot(_snapshot("sleeping", null, "dorm-01/bed-01"))
	bridge._handle_semantic_snapshot(_snapshot("idle", null, null))
	_check(actor.furniture_anchor_id.is_empty() and actor.runtime_posture() == "idle", "unknown terminal did not exit pose")
	var guarded_position := actor.global_position
	for flag: Variant in [false, 1, "true"]:
		actor.set_meta("observer_presentation", flag)
		_check(not actor.observer_present_anchor(bed, "dorm-01/bed-01", "sleeping").is_empty(), "view helper accepted authority actor")
		_check(not actor.observer_stop_presentation() and actor.global_position == guarded_position, "unguarded helper mutated authority actor")
	actor.set_meta("observer_presentation", true)
	bridge._handle_camera_command({"action": "set_local_presentation_paused", "paused": true})
	_check(nest.observer_presentation_paused(), "local pause boundary lost")
	var paused_position := actor.global_position
	bridge._handle_semantic_snapshot(_snapshot("idle", null, "courtyard/activity"))
	_check(actor.global_position == paused_position, "paused viewer applied a completed pose")
	bridge._handle_camera_command({"action": "set_local_presentation_paused", "paused": false})
	_check(not nest.observer_presentation_paused(), "local resume boundary lost")
	presentation._process(0.0)
	_check(actor.global_position.is_equal_approx(paused_position), "resume teleported the resident")
	await _wait_arrival(actor)
	_check(actor.global_position.distance_to(activity.global_position) < 0.44, "resume lost latest real state")
	var explicit_mock := _snapshot("idle", null, null)
	explicit_mock["entities"]["saevi-1"]["mock_motion"] = {"mode": "sleep", "sequence": 20}
	_check(not bool(presentation.get("_local_mock_wander_enabled")), "product random mock unexpectedly enabled")
	bridge._handle_semantic_snapshot(explicit_mock)
	_check(actor.active_command_id.begins_with("observer-mock-wander-"), "explicit authority mock was gated by local random setting")
	_check(actor.visible, "explicit authority replay did not display actor")
	var mock_command := actor.active_command_id
	var mock_deadline := int(actor.get("_deadline_msec"))
	var repeated_mock := _snapshot("idle", null, null)
	repeated_mock["entities"]["saevi-1"]["mock_motion"] = {"mode": "sleep", "sequence": 20}
	bridge._handle_semantic_snapshot(repeated_mock)
	_check(actor.active_command_id == mock_command and int(actor.get("_deadline_msec")) == mock_deadline, "duplicate authority mock restarted navigation")
	var priority_real := _snapshot("walking", "priority-real", "dorm-01/bed-01")
	priority_real["entities"]["saevi-1"]["mock_motion"] = {"mode": "sleep", "sequence": 21}
	bridge._handle_semantic_snapshot(priority_real)
	_check(actor.active_command_id == "observer-real-action-priority-real", "explicit mock overrode a real semantic anchor")
	var replace_real := _snapshot("idle", null, null)
	replace_real["entities"]["saevi-1"]["mock_motion"] = {"mode": "sleep", "sequence": 22}
	bridge._handle_semantic_snapshot(replace_real)
	_check(actor.active_command_id.begins_with("observer-mock-wander-"), "explicit mock could not replace prior real replay")
	bridge._handle_semantic_snapshot(_snapshot("idle", null, null))
	_check(actor.active_command_id.is_empty(), "cleared authority mock kept moving")
	var empty := _snapshot("idle", null, null)
	empty["entities"] = {}
	empty["entity_revisions"] = {}
	bridge._handle_semantic_snapshot(empty)
	_check(characters.get_child_count() == 0, "stale avatar not removed")
	if not _errors.is_empty():
		for error: String in _errors:
			push_error(error)
		quit(1)
		return
	print("PASS observer real actions: strict anchor, pending/duplicate walk, mid-walk pause/resume, authored bed/chair, cancellation, helper guard, explicit authority mock priority")
	quit(0)


func _snapshot(posture: String, command: Variant, anchor: Variant) -> Dictionary:
	_sequence += 1
	return {
		"channel": "elfienest.observer", "version": 1, "kind": "semantic_snapshot",
		"protocol": 3, "generation": 1, "sequence": _sequence,
		"scope": {"kind": "room", "room_id": "local-nest"},
		"entity_revisions": {"saevi-1": _sequence},
		"entities": {"saevi-1": {
			"room_id": "local-nest", "zone_id": "dorm-01", "posture": posture,
			"active": true, "active_command_id": command, "action_anchor_id": anchor,
			"species_id": "saevi", "appearance": {},
			"home_anchor_id": "dorm-01/bed-01", "mock_motion": null,
		}},
	}


func _wait_arrival(actor: ElfieActor) -> void:
	for frame in range(900):
		await physics_frame
		if actor.active_command_id.is_empty():
			await process_frame
			await process_frame
			return


func _marker(nest: ReplayNest, id: String, kind: String, approach: Vector3, posture: String = "") -> Marker3D:
	var marker := Marker3D.new()
	nest.add_child(marker)
	marker.position = approach
	marker.set_meta("kind", kind)
	marker.set_meta("zone_id", id.get_slice("/", 0))
	if not posture.is_empty():
		marker.set_meta("interaction_posture", posture)
		marker.set_meta("interaction_transform", Transform3D(Basis.IDENTITY, approach + Vector3.UP * 0.5))
	nest.markers[id] = marker
	return marker


func _add_navigation(nest: ReplayNest) -> void:
	var floor_body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(12, 0.1, 12)
	shape.shape = box
	shape.position.y = -0.05
	floor_body.add_child(shape)
	nest.add_child(floor_body)
	var region := NavigationRegion3D.new()
	region.name = "ReplayNavigation"
	var mesh := NavigationMesh.new()
	mesh.set_vertices(PackedVector3Array([Vector3(-6, 0.02, -6), Vector3(-6, 0.02, 6), Vector3(6, 0.02, 6), Vector3(6, 0.02, -6)]))
	mesh.add_polygon(PackedInt32Array([0, 1, 2, 3]))
	region.navigation_mesh = mesh
	nest.add_child(region)


func _check_contact(actor: ElfieActor, marker: Marker3D) -> void:
	var hips := actor._furniture_hips()
	_check(not hips.is_empty(), "authored pose has no actual skeleton hips")
	if hips.is_empty():
		return
	var skeleton := hips["skeleton"] as Skeleton3D
	var contact := skeleton.to_global(skeleton.get_bone_global_pose(int(hips["bone"])).origin)
	_check(contact.distance_to((marker.get_meta("interaction_transform") as Transform3D).origin) < 0.001, "pose is not at authored contact")


func _check(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)
