class_name NestActorRuntimeController
extends Node

const ACTOR_CATALOG := preload("res://runtime/actor/actor_catalog.gd")
const MOCK_WANDER_CONTROLLER := preload("res://runtime/actor/mock_wander_controller.gd")

signal runtime_event(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
)

var _nest: ModularNest
var _characters: Node3D
var _actor_scenes: Dictionary
var _actors: Dictionary = {}
var _actor_catalog: Dictionary = {}
var _command_actor_ids: Dictionary = {}
var _command_metadata: Dictionary = {}
var _terminal_commands: Dictionary = {}
var _install_actor_animations := true
var _mock_command_actor_ids: Dictionary = {}
var _mock_wander


func setup(
	nest: ModularNest,
	characters: Node3D,
	actor_scenes: Dictionary,
	install_actor_animations: bool = true,
	enable_mock_wander: bool = false,
) -> void:
	_nest = nest
	_characters = characters
	_actor_scenes = actor_scenes
	_install_actor_animations = install_actor_animations
	_mock_wander = MOCK_WANDER_CONTROLLER.new()
	add_child(_mock_wander)
	_mock_wander.setup(self, _nest, enable_mock_wander)
	_mock_wander.motion_changed.connect(_on_mock_motion_changed)


func sync_actors(raw_actors: Variant) -> Dictionary:
	var result := ACTOR_CATALOG.normalize(_nest, _actor_scenes, raw_actors)
	if not bool(result.get("accepted", false)):
		return result
	var normalized := result["actors"] as Array

	var expected_ids := {}
	for actor_data: Dictionary in normalized:
		var actor_id := String(actor_data["actor_id"])
		expected_ids[actor_id] = true
		var fingerprint := JSON.stringify(actor_data)
		if (
			_actor_catalog.get(actor_id, "") == fingerprint
			and _actors.has(actor_id)
		):
			continue
		_remove_actor(actor_id)
		var actor := _create_actor(actor_data)
		if actor == null:
			return {"accepted": false, "code": "actor_instantiation_failed"}
		_actors[actor_id] = actor
		_actor_catalog[actor_id] = fingerprint

	var stale_ids: Array[String] = []
	for actor_id: Variant in _actors.keys():
		if not expected_ids.has(actor_id):
			stale_ids.append(String(actor_id))
	for actor_id in stale_ids:
		_remove_actor(actor_id)

	var synced_ids: Array[String] = []
	for actor_data: Dictionary in normalized:
		synced_ids.append(String(actor_data["actor_id"]))
	return {
		"accepted": true,
		"actor_ids": synced_ids,
		"snapshot": world_snapshot(),
	}


func world_snapshot() -> Dictionary:
	var snapshot := ACTOR_CATALOG.snapshot(_nest, _actors, _actor_catalog)
	if _mock_wander == null:
		return snapshot
	for actor_data: Dictionary in snapshot["actors"] as Array:
		var motion: Variant = _mock_wander.motion_for(String(actor_data["actor_id"]))
		if not motion.is_empty():
			actor_data["mock_motion"] = motion
	return snapshot


func actor(actor_id: String) -> ElfieActor:
	return _actors.get(actor_id) as ElfieActor


func actor_instances() -> Array[Node3D]:
	var result: Array[Node3D] = []
	for value: Variant in _actors.values():
		if value is Node3D:
			result.append(value as Node3D)
	return result


func execute_intent(command: Dictionary) -> void:
	var command_id := String(command.get("command_id", ""))
	var actor_id := String(command.get("actor_id", ""))
	if command_id.is_empty() or _command_actor_ids.has(command_id):
		return
	_command_actor_ids[command_id] = actor_id
	_command_metadata[command_id] = {
		"intent_id": String(command.get("intent_id", command_id)),
		"body_generation": maxi(int(command.get("body_generation", 1)), 1),
	}
	_emit_command_event("intent_accepted", command_id, actor_id)
	var actor_instance := actor(actor_id)
	if actor_instance == null:
		_emit_terminal(command_id, actor_id, "failed", "actor_not_found")
		return
	if _mock_wander != null:
		_mock_wander.cancel_for_real_intent(actor_id)
	var intent := String(command.get("intent", ""))
	if intent == "move_forward":
		_execute_move_forward(command, actor_instance)
		return
	if intent == "turn":
		_execute_turn(command, actor_instance)
		return
	if intent != "move_to_anchor":
		_execute_non_movement_intent(command, actor_instance)
		return
	var anchor_id := String(command.get("anchor_id", ""))
	var marker := _nest.resolve_anchor(anchor_id)
	if marker == null:
		_emit_terminal(command_id, actor_id, "failed", "anchor_not_found")
		return
	var deadline_seconds := float(command.get("deadline_seconds", 0.0))
	if deadline_seconds <= 0.0:
		_emit_terminal(command_id, actor_id, "failed", "invalid_deadline")
		return
	if not actor_instance.move_to(
		command_id,
		marker.global_position,
		deadline_seconds,
	):
		_emit_terminal(command_id, actor_id, "failed", "actor_busy")
		return
	_emit_command_event("intent_started", command_id, actor_id)


func start_mock_move(
	actor_id: String,
	command_id: String,
	target_position: Vector3,
	deadline_seconds: float,
) -> bool:
	if (
		_mock_wander == null
		or not MOCK_WANDER_CONTROLLER._is_mock_command(command_id)
		or command_id.is_empty()
		or _mock_command_actor_ids.has(command_id)
	):
		return false
	var actor_instance := actor(actor_id)
	if actor_instance == null:
		return false
	_mock_command_actor_ids[command_id] = actor_id
	if not actor_instance.move_to(command_id, target_position, deadline_seconds):
		_mock_command_actor_ids.erase(command_id)
		return false
	return true


func cancel_mock_move(actor_id: String, reason: String) -> bool:
	var actor_instance := actor(actor_id)
	if actor_instance == null:
		return false
	var command_id := actor_instance.active_command_id
	if not MOCK_WANDER_CONTROLLER._is_mock_command(command_id):
		return false
	return actor_instance.cancel_navigation(reason)


func cancel_intent(command: Dictionary) -> void:
	var command_id := String(command.get("command_id", ""))
	var actor_id := String(_command_actor_ids.get(command_id, ""))
	if actor_id.is_empty() or _terminal_commands.has(command_id):
		return
	var actor_instance := actor(actor_id)
	if actor_instance == null or actor_instance.active_command_id != command_id:
		_emit_terminal(command_id, actor_id, "failed", "command_not_active")
		return
	actor_instance.cancel_navigation("cancelled_by_controller")


func _create_actor(actor_data: Dictionary) -> ElfieActor:
	var species := String(actor_data["species"])
	var scene := _actor_scenes[species] as PackedScene
	var instance := scene.instantiate()
	if not instance is ElfieActor:
		instance.queue_free()
		return null
	var actor := instance as ElfieActor
	actor.install_shared_animations = _install_actor_animations
	_characters.add_child(actor)
	var spawn_anchor := _nest.resolve_anchor(
		String(actor_data["spawn_anchor_id"])
	)
	actor.configure(
		String(actor_data["actor_id"]),
		spawn_anchor.global_position,
		actor_data["appearance"] as Dictionary,
	)
	actor.set_meta("species", species)
	actor.set_meta("spawn_anchor_id", String(actor_data["spawn_anchor_id"]))
	actor.navigation_terminal.connect(
		_on_actor_navigation_terminal.bind(String(actor_data["actor_id"]))
	)
	if _mock_wander != null:
		actor.navigation_terminal.connect(
			_mock_wander.handle_navigation_terminal.bind(String(actor_data["actor_id"]))
		)
	actor.movement_blocked.connect(
		_on_actor_movement_blocked.bind(String(actor_data["actor_id"]))
	)
	actor.tactile_contact.connect(
		_on_actor_tactile_contact.bind(String(actor_data["actor_id"]))
	)
	return actor


func _remove_actor(actor_id: String) -> void:
	var existing := _actors.get(actor_id) as ElfieActor
	if existing != null:
		if not existing.active_command_id.is_empty():
			var command_id := existing.active_command_id
			var is_mock_command := MOCK_WANDER_CONTROLLER._is_mock_command(command_id)
			existing.cancel_navigation("actor_removed")
			if not is_mock_command and not _terminal_commands.has(command_id):
				_emit_terminal(
					command_id,
					actor_id,
					"cancelled",
					"actor_removed",
				)
		_characters.remove_child(existing)
		existing.queue_free()
	_actors.erase(actor_id)
	_actor_catalog.erase(actor_id)


func _on_actor_navigation_terminal(
	command_id: String,
	status: String,
	reason: String,
	actor_id: String,
) -> void:
	if _mock_command_actor_ids.has(command_id):
		_mock_command_actor_ids.erase(command_id)
		return
	_emit_terminal(command_id, actor_id, status, reason)


func _on_actor_movement_blocked(command_id: String, actor_id: String) -> void:
	if _mock_command_actor_ids.has(command_id):
		return
	var payload := {"command_id": command_id, "actor_id": actor_id}
	payload.merge(_command_metadata.get(command_id, {}))
	runtime_event.emit(
		"movement_blocked",
		payload,
		command_id,
	)


func _on_actor_tactile_contact(contact: Dictionary, actor_id: String) -> void:
	var actor_instance := actor(actor_id)
	var cause_id := "" if actor_instance == null else actor_instance.active_command_id
	runtime_event.emit(
		"tactile_contact",
		contact.merged({"actor_id": actor_id}),
		cause_id,
	)


func _on_mock_motion_changed() -> void:
	runtime_event.emit("world_snapshot", world_snapshot(), "mock-wander")


func _execute_non_movement_intent(
	command: Dictionary,
	actor_instance: ElfieActor,
) -> void:
	var command_id := String(command["command_id"])
	var actor_id := String(command["actor_id"])
	var intent := String(command.get("intent", ""))
	if intent == "speak":
		_emit_command_event("intent_started", command_id, actor_id)
		actor_instance.play_runtime_speech()
		_emit_terminal(command_id, actor_id, "completed", "")
		return
	if intent == "emotion_expression":
		var expression := String(command.get("expression", ""))
		if not actor_instance.play_runtime_expression(expression):
			_emit_terminal(
				command_id,
				actor_id,
				"failed",
				"unsupported_expression",
			)
			return
		_emit_command_event("intent_started", command_id, actor_id)
		_emit_terminal(command_id, actor_id, "completed", "")
		return
	_emit_terminal(command_id, actor_id, "failed", "unsupported_intent")


func _execute_move_forward(command: Dictionary, actor_instance: ElfieActor) -> void:
	var command_id := String(command["command_id"])
	var actor_id := String(command["actor_id"])
	var distance := float(command.get("distance", 0.0))
	var deadline_seconds := float(command.get("deadline_seconds", 0.0))
	if distance <= 0.0:
		_emit_terminal(command_id, actor_id, "failed", "invalid_distance")
		return
	if deadline_seconds <= 0.0:
		_emit_terminal(command_id, actor_id, "failed", "invalid_deadline")
		return
	# ElfieActor models use +Z as the visual forward direction.
	var forward := actor_instance.global_transform.basis.z.normalized()
	var target_position := actor_instance.global_position + forward * distance
	if not actor_instance.move_to(command_id, target_position, deadline_seconds):
		_emit_terminal(command_id, actor_id, "failed", "actor_busy")
		return
	_emit_command_event("intent_started", command_id, actor_id)


func _execute_turn(command: Dictionary, actor_instance: ElfieActor) -> void:
	var command_id := String(command["command_id"])
	var actor_id := String(command["actor_id"])
	var angle_degrees := float(command.get("angle_degrees", 0.0))
	var deadline_seconds := float(command.get("deadline_seconds", 0.0))
	if deadline_seconds <= 0.0:
		_emit_terminal(command_id, actor_id, "failed", "invalid_deadline")
		return
	if not actor_instance.active_command_id.is_empty():
		_emit_terminal(command_id, actor_id, "failed", "actor_busy")
		return
	_emit_command_event("intent_started", command_id, actor_id)
	actor_instance.rotate_y(deg_to_rad(angle_degrees))
	_emit_terminal(command_id, actor_id, "completed", "")


func _emit_command_event(
	event_name: String,
	command_id: String,
	actor_id: String,
) -> void:
	var payload := {"command_id": command_id, "actor_id": actor_id}
	payload.merge(_command_metadata.get(command_id, {}))
	runtime_event.emit(
		event_name,
		payload,
		command_id,
	)


func _emit_terminal(
	command_id: String,
	actor_id: String,
	status: String,
	reason: String,
) -> void:
	if _terminal_commands.has(command_id):
		return
	_terminal_commands[command_id] = true
	var payload := {
		"command_id": command_id,
		"actor_id": actor_id,
		"status": status,
	}
	payload.merge(_command_metadata.get(command_id, {}))
	if not reason.is_empty():
		payload["reason"] = reason
	runtime_event.emit("intent_terminal", payload, command_id)
