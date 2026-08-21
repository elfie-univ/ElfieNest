class_name ObserverPresentationController
extends Node

const MOCK_WANDER_TARGET := preload("res://runtime/actor/mock_wander_target.gd")
const MOCK_COMMAND_PREFIX := "observer-mock-wander-"
## Temporary monitor-only visual Mock; remove this block when real control lands.
const LOCAL_MOCK_COMMAND_PREFIX := "observer-local-mock-wander-"
const LOCAL_MOCK_ACTIVE_START_HOUR := 6
const LOCAL_MOCK_ACTIVE_END_HOUR := 24
const LOCAL_MOCK_FIRST_MOVE_DELAY_MSEC := 1000
const LOCAL_MOCK_REST_MIN_SECONDS := 5.0
const LOCAL_MOCK_REST_MAX_SECONDS := 14.0
const LOCAL_MOCK_MOVE_DEADLINE_SECONDS := 60.0

var _nest: ModularNest
var _characters: Node3D
var _actor_scenes: Dictionary
var _actors: Dictionary = {}
var _fingerprints: Dictionary = {}
var _pending_motions: Dictionary = {}
var _local_mock_wander_enabled := false
var _local_mock_random := RandomNumberGenerator.new()
var _local_mock_states: Dictionary = {}


func setup(
	nest: ModularNest,
	characters: Node3D,
	actor_scenes: Dictionary,
	enable_local_mock_wander: bool = false,
) -> void:
	_nest = nest
	_characters = characters
	_actor_scenes = actor_scenes
	_local_mock_wander_enabled = enable_local_mock_wander
	if _local_mock_wander_enabled:
		_local_mock_random.randomize()


func _process(_delta: float) -> void:
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
	if _local_mock_wander_enabled:
		_process_local_mock_wander()


func apply_snapshot(snapshot: Dictionary) -> void:
	var entities: Variant = snapshot.get("entities", {})
	if not entities is Dictionary:
		return
	var expected_ids: Dictionary = {}
	for raw_id: Variant in (entities as Dictionary).keys():
		var actor_id := String(raw_id)
		var entity: Variant = (entities as Dictionary).get(raw_id)
		if not entity is Dictionary or not _valid_entity(actor_id, entity as Dictionary):
			continue
		expected_ids[actor_id] = true
		var fingerprint := _render_fingerprint(entity as Dictionary)
		if _actors.has(actor_id) and _fingerprints.get(actor_id, "") == fingerprint:
			_set_observer_command_state(_actors[actor_id] as ElfieActor, entity as Dictionary)
			_apply_motion(_actors[actor_id] as ElfieActor, entity as Dictionary)
			continue
		_remove_actor(actor_id)
		var actor := _create_actor(actor_id, entity as Dictionary)
		if actor == null:
			continue
		_actors[actor_id] = actor
		_fingerprints[actor_id] = fingerprint
		_set_observer_command_state(actor, entity as Dictionary)
		_apply_motion(actor, entity as Dictionary)

	var stale_ids: Array[String] = []
	for raw_id: Variant in _actors.keys():
		var actor_id := String(raw_id)
		if not expected_ids.has(actor_id):
			stale_ids.append(actor_id)
	for actor_id in stale_ids:
		_remove_actor(actor_id)


func _valid_entity(actor_id: String, entity: Dictionary) -> bool:
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
	# Keep the temporary observer replay lightweight; movement remains visible even
	# without installing the authority's shared animation library.
	actor.install_shared_animations = false
	_characters.add_child(actor)
	var anchor := _nest.resolve_anchor(String(entity["home_anchor_id"]))
	if anchor == null:
		_characters.remove_child(actor)
		actor.queue_free()
		return null
	actor.species_id = species
	actor.configure(actor_id, anchor.global_position, entity["appearance"] as Dictionary)
	actor.ground_visual_to_floor(anchor.global_position.y)
	actor.set_meta("observer_presentation", true)
	actor.set_meta("species", species)
	actor.set_meta("home_anchor_id", String(entity["home_anchor_id"]))
	return actor


func _render_fingerprint(entity: Dictionary) -> String:
	return JSON.stringify({
		"room_id": entity.get("room_id"),
		"species_id": entity.get("species_id"),
		"appearance": entity.get("appearance", {}),
		"home_anchor_id": entity.get("home_anchor_id"),
	})


func _set_observer_command_state(actor: ElfieActor, entity: Dictionary) -> void:
	var raw_command_id: Variant = entity.get("active_command_id", null)
	actor.set_meta(
		"observer_active_command_id",
		String(raw_command_id) if raw_command_id is String else "",
	)


func _apply_motion(actor: ElfieActor, entity: Dictionary) -> void:
	var raw_motion: Variant = entity.get("mock_motion", null)
	if raw_motion == null:
		_pending_motions.erase(actor.elfie_id)
		_stop_motion(actor)
		return
	if not raw_motion is Dictionary:
		_pending_motions.erase(actor.elfie_id)
		return
	var motion := raw_motion as Dictionary
	if actor.active_command_id.begins_with(LOCAL_MOCK_COMMAND_PREFIX):
		_stop_local_mock_motion(actor, "authority_mock_motion")
	var sequence := int(motion.get("sequence", 0))
	if sequence < 1:
		_pending_motions.erase(actor.elfie_id)
		_stop_motion(actor)
		return
	if int(actor.get_meta("observer_mock_motion_sequence", -1)) == sequence:
		return
	if not actor.active_command_id.is_empty():
		if actor.active_command_id.begins_with(MOCK_COMMAND_PREFIX):
			actor.cancel_navigation("mock_motion_replaced")
		else:
			return
	var mode := String(motion.get("mode", "wander"))
	var target: Variant
	if mode == "sleep":
		var home_anchor := _nest.resolve_anchor(
			String(actor.get_meta("home_anchor_id", ""))
		)
		if home_anchor == null or String(home_anchor.get_meta("kind", "")) != "bed":
			_pending_motions[actor.elfie_id] = entity.duplicate(true)
			_stop_motion(actor)
			return
		target = home_anchor.global_position
	elif mode == "wander":
		var waypoint := int(motion.get("waypoint", -1))
		target = MOCK_WANDER_TARGET.target_for(
			_nest,
			actor,
			waypoint,
			sequence,
		)
	else:
		_pending_motions.erase(actor.elfie_id)
		_stop_motion(actor)
		return
	if not target is Vector3:
		_pending_motions[actor.elfie_id] = entity.duplicate(true)
		_stop_motion(actor)
		return
	var command_suffix := "sleep-%d" % sequence if mode == "sleep" else "%d" % sequence
	var command_id := "%s%s-%s" % [MOCK_COMMAND_PREFIX, actor.elfie_id, command_suffix]
	if not actor.move_to(command_id, target as Vector3, 30.0):
		_pending_motions[actor.elfie_id] = entity.duplicate(true)
		_stop_motion(actor)
		return
	_pending_motions.erase(actor.elfie_id)
	actor.set_meta("observer_mock_motion_sequence", sequence)
	actor.set_physics_process(true)


func _stop_motion(actor: ElfieActor) -> void:
	if actor.active_command_id.begins_with(MOCK_COMMAND_PREFIX):
		actor.cancel_navigation("mock_motion_stopped")
		actor.set_meta("observer_mock_motion_sequence", -1)
		actor.set_physics_process(false)


func _process_local_mock_wander() -> void:
	var now_msec := Time.get_ticks_msec()
	var live_ids: Dictionary = {}
	var active_window := _is_local_mock_active_window()
	var presentation_paused := _nest.observer_presentation_paused()
	for raw_actor_id: Variant in _actors.keys():
		var actor_id := String(raw_actor_id)
		var actor := _actors.get(actor_id) as ElfieActor
		if actor == null:
			continue
		live_ids[actor_id] = true
		_ensure_local_mock_state(actor_id, now_msec)
		if not active_window or presentation_paused or _has_external_observer_command(actor):
			_pause_local_mock_motion(actor, now_msec)
			continue
		_advance_local_mock_actor(actor, now_msec)
	for raw_actor_id: Variant in _local_mock_states.keys():
		if not live_ids.has(String(raw_actor_id)):
			_local_mock_states.erase(raw_actor_id)


func _ensure_local_mock_state(actor_id: String, now_msec: int) -> void:
	if _local_mock_states.has(actor_id):
		return
	_local_mock_states[actor_id] = {
		"command_id": "",
		"phase": "resting",
		"sequence": 0,
		"waypoint": -1,
		"next_at_msec": now_msec + LOCAL_MOCK_FIRST_MOVE_DELAY_MSEC,
	}


func _advance_local_mock_actor(actor: ElfieActor, now_msec: int) -> void:
	var actor_id := actor.elfie_id
	var state := _local_mock_states[actor_id] as Dictionary
	var command_id := String(state.get("command_id", ""))
	if not command_id.is_empty():
		if actor.active_command_id == command_id:
			return
		state["command_id"] = ""
		state["phase"] = "resting"
		state["next_at_msec"] = now_msec + _local_mock_rest_msec()
		_local_mock_states[actor_id] = state
		return
	if String(state.get("phase", "")) == "paused":
		state["phase"] = "resting"
		state["next_at_msec"] = now_msec + LOCAL_MOCK_FIRST_MOVE_DELAY_MSEC
		_local_mock_states[actor_id] = state
		return
	if not actor.active_command_id.is_empty() or now_msec < int(state.get("next_at_msec", now_msec)):
		return

	var total_waypoints := MOCK_WANDER_TARGET.waypoint_count(_nest)
	if total_waypoints <= 0:
		state["next_at_msec"] = now_msec + 1000
		_local_mock_states[actor_id] = state
		return
	var previous_waypoint := int(state.get("waypoint", -1))
	var waypoint := _local_mock_random.randi_range(0, total_waypoints - 1)
	if total_waypoints > 1 and waypoint == previous_waypoint:
		waypoint = (waypoint + 1) % total_waypoints
	var sequence := int(state.get("sequence", 0)) + 1
	var target: Variant = MOCK_WANDER_TARGET.target_for(
		_nest,
		actor,
		waypoint,
		sequence,
	)
	if not target is Vector3:
		state["next_at_msec"] = now_msec + 1000
		_local_mock_states[actor_id] = state
		return
	var local_command_id := "%s%s-%d" % [
		LOCAL_MOCK_COMMAND_PREFIX,
		actor_id,
		sequence,
	]
	if not actor.move_to(
		local_command_id,
		target as Vector3,
		LOCAL_MOCK_MOVE_DEADLINE_SECONDS,
	):
		state["next_at_msec"] = now_msec + 1000
		_local_mock_states[actor_id] = state
		return
	state["command_id"] = local_command_id
	state["phase"] = "wandering"
	state["sequence"] = sequence
	state["waypoint"] = waypoint
	_local_mock_states[actor_id] = state
	actor.set_physics_process(true)


func _pause_local_mock_motion(actor: ElfieActor, now_msec: int) -> void:
	var state := _local_mock_states.get(actor.elfie_id) as Dictionary
	if state == null:
		return
	if actor.active_command_id.begins_with(LOCAL_MOCK_COMMAND_PREFIX):
		actor.cancel_navigation("local_mock_paused")
		actor.set_physics_process(false)
	state["command_id"] = ""
	state["phase"] = "paused"
	state["next_at_msec"] = now_msec + LOCAL_MOCK_FIRST_MOVE_DELAY_MSEC
	_local_mock_states[actor.elfie_id] = state


func _stop_local_mock_motion(actor: ElfieActor, reason: String) -> void:
	if actor.active_command_id.begins_with(LOCAL_MOCK_COMMAND_PREFIX):
		actor.cancel_navigation(reason)
		actor.set_physics_process(false)
	_local_mock_states.erase(actor.elfie_id)


func _has_external_observer_command(actor: ElfieActor) -> bool:
	var semantic_command_id := String(
		actor.get_meta("observer_active_command_id", "")
	)
	if not semantic_command_id.is_empty():
		return true
	return (
		not actor.active_command_id.is_empty()
		and not actor.active_command_id.begins_with(LOCAL_MOCK_COMMAND_PREFIX)
	)


func _is_local_mock_active_window() -> bool:
	var time := Time.get_time_dict_from_system()
	var hour := int(time.get("hour", 0))
	return (
		hour >= LOCAL_MOCK_ACTIVE_START_HOUR
		and hour < LOCAL_MOCK_ACTIVE_END_HOUR
	)


func _local_mock_rest_msec() -> int:
	return roundi(
		_local_mock_random.randf_range(
			LOCAL_MOCK_REST_MIN_SECONDS,
			LOCAL_MOCK_REST_MAX_SECONDS,
		) * 1000.0
	)


func _remove_actor(actor_id: String) -> void:
	_pending_motions.erase(actor_id)
	_local_mock_states.erase(actor_id)
	var actor := _actors.get(actor_id) as ElfieActor
	if actor != null:
		if actor.active_command_id.begins_with(LOCAL_MOCK_COMMAND_PREFIX):
			actor.cancel_navigation("observer_actor_removed")
		if actor.active_command_id.begins_with(MOCK_COMMAND_PREFIX):
			actor.cancel_navigation("observer_actor_removed")
		if actor.get_parent() == _characters:
			_characters.remove_child(actor)
		actor.queue_free()
	_actors.erase(actor_id)
	_fingerprints.erase(actor_id)
