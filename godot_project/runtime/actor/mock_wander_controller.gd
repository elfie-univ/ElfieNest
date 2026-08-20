class_name MockWanderController
extends Node

const TARGET_RESOLVER := preload("res://runtime/actor/mock_wander_target.gd")
const COMMAND_PREFIX := "mock-wander-"
const ACTIVE_START_HOUR := 6
const ACTIVE_END_HOUR := 24
const WAIT_MIN_SECONDS := 4.0
const WAIT_MAX_SECONDS := 10.0
const REST_MIN_SECONDS := 5.0
const REST_MAX_SECONDS := 14.0
const MOVE_DEADLINE_SECONDS := 60.0

signal motion_changed

var _actor_controller: NestActorRuntimeController
var _nest: ModularNest
var _enabled := false
var _random := RandomNumberGenerator.new()
var _states: Dictionary = {}


func setup(
	actor_controller: NestActorRuntimeController,
	nest: ModularNest,
	enabled: bool,
) -> void:
	_actor_controller = actor_controller
	_nest = nest
	_enabled = enabled
	_random.randomize()
	set_process(enabled)


func motion_for(actor_id: String) -> Dictionary:
	var state: Variant = _states.get(actor_id)
	if not state is Dictionary:
		return {}
	var motion: Variant = (state as Dictionary).get("motion", {})
	return motion.duplicate(true) if motion is Dictionary else {}


func cancel_for_real_intent(actor_id: String) -> void:
	var state: Variant = _states.get(actor_id)
	if not state is Dictionary:
		return
	var actor := _actor_controller.actor(actor_id)
	if actor != null and _is_mock_command(String((state as Dictionary).get("command_id", ""))):
		_actor_controller.cancel_mock_move(actor_id, "preempted_by_real_intent")
	else:
		_clear_motion(actor_id, Time.get_ticks_msec())


func _process(_delta: float) -> void:
	if not _enabled:
		return
	var now_msec := Time.get_ticks_msec()
	var live_ids: Dictionary = {}
	for actor_node: Node3D in _actor_controller.actor_instances():
		if not actor_node is ElfieActor:
			continue
		var actor := actor_node as ElfieActor
		var actor_id := actor.elfie_id
		live_ids[actor_id] = true
		_ensure_state(actor_id, now_msec)
		if not _is_active_window():
			_sleep_actor(actor, now_msec)
			continue
		if not _wake_actor(actor, now_msec):
			continue
		_advance_actor(actor, now_msec)
	for actor_id: Variant in _states.keys():
		if not live_ids.has(actor_id):
			_states.erase(actor_id)


func _ensure_state(actor_id: String, now_msec: int) -> void:
	if _states.has(actor_id):
		return
	_states[actor_id] = {
		"command_id": "",
		"motion": {},
		"phase": "resting",
		"sequence": 0,
		"waypoint": -1,
		"next_at_msec": now_msec + _random_wait_msec(),
	}


func _advance_actor(actor: ElfieActor, now_msec: int) -> void:
	var actor_id := actor.elfie_id
	var state := _states[actor_id] as Dictionary
	var command_id := String(state.get("command_id", ""))
	if not command_id.is_empty():
		if actor.active_command_id == command_id:
			return
		_clear_motion(actor_id, now_msec)
		state = _states[actor_id] as Dictionary
	if not actor.active_command_id.is_empty():
		return
	if now_msec < int(state.get("next_at_msec", now_msec)):
		return

	var waypoint := _next_waypoint(int(state.get("waypoint", -1)))
	var sequence := int(state.get("sequence", 0)) + 1
	var target: Variant = TARGET_RESOLVER.target_for(
		_nest,
		actor,
		waypoint,
		sequence,
	)
	if not target is Vector3:
		state["next_at_msec"] = now_msec + 1000
		return
	var mock_command_id := "%s%s-%d" % [COMMAND_PREFIX, actor_id, sequence]
	if not _actor_controller.start_mock_move(
		actor_id,
		mock_command_id,
		target as Vector3,
		MOVE_DEADLINE_SECONDS,
	):
		state["next_at_msec"] = now_msec + 1000
		return
	state["command_id"] = mock_command_id
	state["sequence"] = sequence
	state["waypoint"] = waypoint
	state["motion"] = TARGET_RESOLVER.motion_payload(waypoint, sequence)
	state["phase"] = "wandering"
	_states[actor_id] = state
	motion_changed.emit()


func _sleep_actor(actor: ElfieActor, now_msec: int) -> void:
	var actor_id := actor.elfie_id
	var state := _states[actor_id] as Dictionary
	var command_id := String(state.get("command_id", ""))
	if not command_id.is_empty():
		if actor.active_command_id == command_id:
			if _is_sleep_command(command_id):
				return
			_actor_controller.cancel_mock_move(actor_id, "sleep_window")
			return
		var stale_motion := state.get("motion", {}) as Dictionary
		var had_stale_motion := not stale_motion.is_empty()
		state["command_id"] = ""
		state["motion"] = {}
		state["phase"] = "resting"
		if had_stale_motion:
			motion_changed.emit()
	if not actor.active_command_id.is_empty():
		state["next_at_msec"] = now_msec + 1000
		_states[actor_id] = state
		return
	if String(state.get("phase", "")) == "sleeping":
		return
	var target: Variant = TARGET_RESOLVER.sleep_target(_nest, actor)
	if not target is Vector3:
		state["next_at_msec"] = now_msec + 1000
		_states[actor_id] = state
		return
	var sequence := int(state.get("sequence", 0)) + 1
	var sleep_command_id := "%s%s-sleep-%d" % [COMMAND_PREFIX, actor_id, sequence]
	if not _actor_controller.start_mock_move(
		actor_id,
		sleep_command_id,
		target as Vector3,
		MOVE_DEADLINE_SECONDS,
	):
		state["next_at_msec"] = now_msec + 1000
		_states[actor_id] = state
		return
	state["command_id"] = sleep_command_id
	state["sequence"] = sequence
	state["waypoint"] = -1
	state["motion"] = TARGET_RESOLVER.sleep_motion_payload(sequence)
	state["phase"] = "sleeping"
	_states[actor_id] = state
	motion_changed.emit()


func _wake_actor(actor: ElfieActor, now_msec: int) -> bool:
	var actor_id := actor.elfie_id
	var state := _states[actor_id] as Dictionary
	var command_id := String(state.get("command_id", ""))
	var motion := state.get("motion", {}) as Dictionary
	var is_sleeping := (
		String(state.get("phase", "")) == "sleeping"
		or String(motion.get("mode", "")) == "sleep"
		or _is_sleep_command(command_id)
	)
	if not is_sleeping:
		return true
	if not actor.active_command_id.is_empty():
		if actor.active_command_id == command_id and _is_sleep_command(command_id):
			_actor_controller.cancel_mock_move(actor_id, "active_window")
		return false
	var had_motion := not motion.is_empty()
	state["command_id"] = ""
	state["motion"] = {}
	state["phase"] = "resting"
	state["next_at_msec"] = now_msec + _random_wait_msec()
	_states[actor_id] = state
	if had_motion:
		motion_changed.emit()
	return true


func _stop_for_inactive_window(actor: ElfieActor, now_msec: int) -> void:
	_sleep_actor(actor, now_msec)


func handle_navigation_terminal(
	command_id: String,
	_status: String,
	_reason: String,
	actor_id: String,
) -> void:
	var state: Variant = _states.get(actor_id)
	if not state is Dictionary:
		return
	var state_map := state as Dictionary
	if String(state_map.get("command_id", "")) != command_id:
		return
	if _is_sleep_command(command_id):
		if _status == "completed":
			state_map["command_id"] = ""
			state_map["phase"] = "sleeping"
			state_map["next_at_msec"] = Time.get_ticks_msec() + _random_rest_msec()
			_states[actor_id] = state_map
			motion_changed.emit()
			return
		var sleep_motion := state_map.get("motion", {}) as Dictionary
		var had_sleep_motion := not sleep_motion.is_empty()
		state_map["command_id"] = ""
		state_map["motion"] = {}
		state_map["phase"] = "resting"
		state_map["next_at_msec"] = Time.get_ticks_msec() + 1000
		_states[actor_id] = state_map
		if had_sleep_motion:
			motion_changed.emit()
		return
	_clear_motion(actor_id, Time.get_ticks_msec())


func _clear_motion(actor_id: String, now_msec: int) -> void:
	var state: Variant = _states.get(actor_id)
	if not state is Dictionary:
		return
	var state_map := state as Dictionary
	var motion := state_map.get("motion", {}) as Dictionary
	var had_motion := not motion.is_empty()
	state_map["command_id"] = ""
	state_map["motion"] = {}
	state_map["phase"] = "resting"
	state_map["next_at_msec"] = now_msec + _random_rest_msec()
	_states[actor_id] = state_map
	if had_motion:
		motion_changed.emit()


func _next_waypoint(previous: int) -> int:
	var total_waypoints := TARGET_RESOLVER.waypoint_count(_nest)
	if total_waypoints <= 1:
		return 0
	var waypoint := _random.randi_range(0, total_waypoints - 1)
	if waypoint == previous:
		waypoint = (waypoint + 1) % total_waypoints
	return waypoint


static func is_active_hour(hour: int) -> bool:
	return hour >= ACTIVE_START_HOUR and hour < ACTIVE_END_HOUR


func _is_active_window() -> bool:
	var time := Time.get_time_dict_from_system()
	var hour := int(time.get("hour", 0))
	return is_active_hour(hour)


func _random_wait_msec() -> int:
	return roundi(_random.randf_range(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS) * 1000.0)


func _random_rest_msec() -> int:
	return roundi(_random.randf_range(REST_MIN_SECONDS, REST_MAX_SECONDS) * 1000.0)


static func _is_mock_command(command_id: String) -> bool:
	return command_id.begins_with(COMMAND_PREFIX)


static func _is_sleep_command(command_id: String) -> bool:
	return _is_mock_command(command_id) and command_id.find("-sleep-") >= 0
