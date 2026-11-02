class_name ObserverPresentationController
extends Node

const OBSERVER_BRIDGE := preload("res://runtime/observer/observer_bridge.gd")
const RESIDENT_EFFECTS := preload("res://runtime/observer/resident_effects.gd")
const REAL_COMMAND_PREFIX := "observer-real-action-"

var _nest: ModularNest
var _characters: Node3D
var _actor_scenes: Dictionary
var _actors: Dictionary = {}
var _fingerprints: Dictionary = {}
var _pending_motions: Dictionary = {}
var _pending_arrivals: Dictionary = {}
var _motion_states: Dictionary = {}
var _navigation_ready := false
var _navigation_preparing := false
var _snapshot_generation := 0
var _snapshot_sequence := 0
var _paused_snapshot: Dictionary = {}
var _initial_actor_focus_done := false
var _requested_actor_focus := ""


func setup(
	nest: ModularNest,
	characters: Node3D,
	actor_scenes: Dictionary,
) -> void:
	_nest = nest
	_characters = characters
	_actor_scenes = actor_scenes
	call_deferred("prepare_navigation")


func prepare_navigation() -> void:
	if _navigation_preparing:
		return
	_navigation_preparing = true
	_navigation_ready = false
	if _nest.bake_navigation():
		_navigation_ready = await _nest.wait_for_navigation_sync()
		if _navigation_ready:
			_navigation_ready = _nest.validate_navigation_anchors()
	_navigation_preparing = false


func _process(_delta: float) -> void:
	if _nest.observer_presentation_paused():
		return
	if not _paused_snapshot.is_empty():
		var snapshot := _paused_snapshot
		_paused_snapshot = {}
		apply_snapshot(snapshot)
	for actor_id: String in _pending_arrivals.keys():
		var actor := _actors.get(actor_id) as ElfieActor
		if actor == null:
			_pending_arrivals.erase(actor_id)
			continue
		if not actor.active_command_id.is_empty():
			continue
		var arrival: Dictionary = _pending_arrivals[actor_id]
		_pending_arrivals.erase(actor_id)
		var marker := _nest.resolve_anchor(String(arrival["anchor"]))
		var error := actor.observer_present_anchor(marker, String(arrival["anchor"]), String(arrival["posture"]))
		actor.set_meta("observer_replay_error", error)
	var pending_ids: Array[String] = []
	for raw_id: Variant in _pending_motions.keys():
		pending_ids.append(String(raw_id))
	for actor_id in pending_ids:
		var actor := _actors.get(actor_id) as ElfieActor
		var entity: Variant = _pending_motions.get(actor_id)
		if actor == null or not entity is Dictionary:
			_pending_motions.erase(actor_id)
			continue
		_apply_motion(actor, entity as Dictionary)
	if not _initial_actor_focus_done and not _requested_actor_focus.is_empty():
		var actor := _actors.get(_requested_actor_focus) as ElfieActor
		if actor != null and actor.is_visible_in_tree():
			_initial_actor_focus_done = _nest.select_observer_camera_by_id("elfie-" + _requested_actor_focus)



func apply_snapshot(snapshot: Dictionary) -> void:
	var entities: Variant = snapshot.get("entities", {})
	if not entities is Dictionary:
		return
	var generation := int(snapshot.get("generation", 0))
	var sequence := int(snapshot.get("sequence", 0))
	if generation < _snapshot_generation:
		return
	if generation == _snapshot_generation and sequence <= _snapshot_sequence:
		return
	if _nest.observer_presentation_paused():
		var pending_generation := int(_paused_snapshot.get("generation", 0))
		var pending_sequence := int(_paused_snapshot.get("sequence", 0))
		if generation > pending_generation or (generation == pending_generation and sequence > pending_sequence):
			_paused_snapshot = snapshot.duplicate(true)
		return
	if generation > _snapshot_generation:
		for raw_id: Variant in _actors.keys():
			_stop_real_motion(_actors[raw_id] as ElfieActor)
		_motion_states.clear()
		_pending_motions.clear()
	var scope: Dictionary = snapshot.get("scope", {})
	var requested := str(scope.get("elfie_id", "")) if scope.get("kind") == "elfie" else ""
	if requested != _requested_actor_focus:
		_requested_actor_focus = requested
		_initial_actor_focus_done = false
	_snapshot_generation = generation
	_snapshot_sequence = sequence
	if snapshot.get("environment") is Dictionary:
		_nest.apply_observer_environment(snapshot["environment"],entities)
	var expected_ids: Dictionary = {}
	for raw_id: Variant in (entities as Dictionary).keys():
		var actor_id := String(raw_id)
		var entity: Variant = (entities as Dictionary).get(raw_id)
		if not entity is Dictionary or not _valid_entity(actor_id, entity as Dictionary):
			continue
		expected_ids[actor_id] = true
		var fingerprint := _render_fingerprint(entity as Dictionary)
		if _actors.has(actor_id) and _fingerprints.get(actor_id, "") == fingerprint:
			_apply_motion(_actors[actor_id] as ElfieActor, entity as Dictionary)
			continue
		_remove_actor(actor_id)
		var actor := _create_actor(actor_id, entity as Dictionary)
		if actor == null:
			continue
		_actors[actor_id] = actor
		_fingerprints[actor_id] = fingerprint
		_apply_motion(actor, entity as Dictionary)

	var stale_ids: Array[String] = []
	for raw_id: Variant in _actors.keys():
		var actor_id := String(raw_id)
		if not expected_ids.has(actor_id):
			stale_ids.append(actor_id)
	for actor_id in stale_ids:
		_remove_actor(actor_id)


func _valid_entity(actor_id: String, entity: Dictionary) -> bool:
	if not OBSERVER_BRIDGE._semantic_entity_is_valid(entity):
		return false
	if actor_id.is_empty() or String(entity.get("room_id", "")).strip_edges().is_empty():
		return false
	if typeof(entity.get("active", false)) != TYPE_BOOL or not bool(entity["active"]):
		return false
	var species := String(entity.get("species_id", ""))
	var anchor_id := String(entity.get("home_anchor_id", ""))
	if species.is_empty() or anchor_id.is_empty() or not _actor_scenes.has(species):
		return false
	var anchor := _nest.resolve_anchor(anchor_id)
	if anchor == null or String(anchor.get_meta("kind", "")) != "bed":
		return false
	return entity.get("appearance", {}) is Dictionary


func _create_actor(actor_id: String, entity: Dictionary) -> ElfieActor:
	var species := String(entity["species_id"])
	var scene := _actor_scenes[species] as PackedScene
	var instance := scene.instantiate()
	if not instance is ElfieActor:
		instance.queue_free()
		return null
	var actor := instance as ElfieActor
	# Product main keeps polling the bridge while paused; display physics must not
	# inherit that ALWAYS mode. The child NavigationAgent inherits this boundary.
	actor.process_mode = Node.PROCESS_MODE_PAUSABLE
	actor.set_meta("observer_presentation", true)
	# Home supplies only the initial replay origin, not an invented current action.
	# Do not display a newly seen resident until a real action anchor is known.
	actor.visible = false
	_characters.add_child(actor)
	var anchor := _nest.resolve_anchor(String(entity["home_anchor_id"]))
	if anchor == null:
		_characters.remove_child(actor)
		actor.queue_free()
		return null
	actor.species_id = species
	actor.configure(actor_id, anchor.global_position, entity["appearance"] as Dictionary)
	actor.ground_visual_to_floor(anchor.global_position.y)
	actor.set_meta("species", species)
	actor.set_meta("home_anchor_id", String(entity["home_anchor_id"]))
	actor.set_physics_process(false)
	var effects := RESIDENT_EFFECTS.new()
	effects.name = "ResidentEffects"
	actor.add_child(effects)
	effects.setup(_nest, actor)
	_nest.register_observer_actor_camera(actor_id, actor)
	return actor


func _render_fingerprint(entity: Dictionary) -> String:
	return JSON.stringify({
		"species_id": entity.get("species_id"),
		"appearance": entity.get("appearance", {}),
		"home_anchor_id": entity.get("home_anchor_id"),
	})


func _apply_motion(actor: ElfieActor, entity: Dictionary) -> void:
	var effects := actor.get_node("ResidentEffects")
	if bool(effects.call("apply", entity)):
		return
	var anchor_id: Variant = entity.get("action_anchor_id")
	var command_id: Variant = entity.get("active_command_id")
	var posture := String(entity.get("posture", ""))
	var state := JSON.stringify([anchor_id, command_id, posture])
	if _motion_states.get(actor.elfie_id, "") == state:
		return
	_stop_real_motion(actor)
	if not anchor_id is String or String(anchor_id).is_empty():
		_motion_states[actor.elfie_id] = state
		return
	var marker := _nest.resolve_anchor(String(anchor_id))
	if marker == null:
		_motion_states[actor.elfie_id] = state
		actor.set_meta("observer_replay_error", "anchor_not_found")
		return
	if (
		(posture == "walking" and not command_id is String)
		or (posture == "idle" and command_id != null)
		or posture not in ["walking", "idle", "sleeping", "sitting"]
	):
		_motion_states[actor.elfie_id] = state
		actor.set_meta("observer_replay_error", "inconsistent_action_state")
		return
	if not _navigation_ready:
		_pending_motions[actor.elfie_id] = entity.duplicate(true)
		return
	_pending_motions.erase(actor.elfie_id)
	_motion_states[actor.elfie_id] = state
	actor.set_meta("observer_replay_error", "")
	actor.visible = true
	if posture == "walking":
		var replay_command := REAL_COMMAND_PREFIX + String(command_id)
		if not actor.move_to(replay_command, marker.global_position, 60.0):
			actor.set_meta("observer_replay_error", "local_path_unavailable")
			return
		actor.set_physics_process(true)
		return
	if actor.global_position.distance_to(marker.global_position) > ElfieActor.ARRIVAL_DISTANCE * 2.0:
		if posture != "idle":
			var metadata_error := ElfieActor.furniture_marker_error(marker)
			if not metadata_error.is_empty():
				actor.set_meta("observer_replay_error", metadata_error)
				return
		if not actor.move_to(REAL_COMMAND_PREFIX + "arrival-" + str(_snapshot_sequence), marker.global_position, 120.0):
			actor.set_meta("observer_replay_error", "local_path_unavailable")
			return
		_pending_arrivals[actor.elfie_id] = {"anchor": anchor_id, "posture": posture}
		actor.set_physics_process(true)
		return
	var error := actor.observer_present_anchor(marker, String(anchor_id), posture)
	actor.set_meta("observer_replay_error", error)


func _stop_real_motion(actor: ElfieActor) -> void:
	_pending_arrivals.erase(actor.elfie_id)
	_pending_motions.erase(actor.elfie_id)
	actor.observer_stop_presentation()
	actor.set_meta("observer_replay_error", "")


func _remove_actor(actor_id: String) -> void:
	_nest.remove_observer_actor_camera(actor_id)
	_pending_motions.erase(actor_id)
	_motion_states.erase(actor_id)
	var actor := _actors.get(actor_id) as ElfieActor
	if actor != null:
		_stop_real_motion(actor)
		if actor.get_parent() == _characters:
			_characters.remove_child(actor)
		actor.queue_free()
	_actors.erase(actor_id)
	_fingerprints.erase(actor_id)
