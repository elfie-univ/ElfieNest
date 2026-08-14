class_name NestActorRuntimeController
extends Node

const ACTOR_CATALOG := preload("res://runtime/actor/actor_catalog.gd")
const SEMANTIC_SCENE_INDEX := preload("res://runtime/world/semantic_scene_index.gd")
const VISUAL_MAX_RANGE_SQUARED: float = 324.0

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
var _speech_reach_commands: Dictionary = {}
var _visual_observation_commands: Dictionary = {}
var _terminal_commands: Dictionary = {}
var _install_actor_animations := true


func setup(
	nest: ModularNest,
	characters: Node3D,
	actor_scenes: Dictionary,
	install_actor_animations: bool = true,
) -> void:
	_nest = nest
	_characters = characters
	_actor_scenes = actor_scenes
	_install_actor_animations = install_actor_animations


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
	return ACTOR_CATALOG.snapshot(_nest, _actors, _actor_catalog)


func actor(actor_id: String) -> ElfieActor:
	return _actors.get(actor_id) as ElfieActor


func execute_intent(command: Dictionary) -> void:
	var command_id := String(command.get("command_id", ""))
	var actor_id := String(command.get("actor_id", ""))
	if command_id.is_empty() or _command_actor_ids.has(command_id):
		return
	_command_actor_ids[command_id] = actor_id
	_emit_command_event("intent_accepted", command_id, actor_id)
	var actor_instance := actor(actor_id)
	if actor_instance == null:
		_emit_terminal(command_id, actor_id, "failed", "actor_not_found")
		return
	if String(command.get("intent", "")) != "move_to_anchor":
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


func resolve_speech_reach(command: Dictionary) -> void:
	var command_id := String(command.get("command_id", ""))
	var actor_id := String(command.get("actor_id", ""))
	var profile := String(command.get("acoustic_profile", "normal"))
	if command_id.is_empty() or actor_id.is_empty() or _speech_reach_commands.has(command_id):
		return
	_speech_reach_commands[command_id] = actor_id
	if profile not in ["quiet", "normal", "loud"]:
		return
	var speaker := actor(actor_id)
	if speaker == null:
		return
	var audience: Array[String] = []
	var speaker_zone := _nest.nearest_zone_id(speaker.global_position)
	for other_actor_id: Variant in _actors.keys():
		if String(other_actor_id) == actor_id:
			continue
		var other_actor := _actors[other_actor_id] as ElfieActor
		if _nest.nearest_zone_id(other_actor.global_position) == speaker_zone:
			audience.append(String(other_actor_id))
	audience.sort()
	runtime_event.emit(
		"speech_reach",
		{
			"command_id": command_id,
			"actor_id": actor_id,
			"zone_id": speaker_zone,
			"audience_actor_ids": audience,
		},
		command_id,
	)


func resolve_visual_observation(command: Dictionary) -> void:
	var observation_id := String(command.get("observation_id", ""))
	var actor_id := String(command.get("actor_id", ""))
	if (
		observation_id.is_empty()
		or actor_id.is_empty()
		or _visual_observation_commands.has(observation_id)
	):
		return
	_visual_observation_commands[observation_id] = actor_id
	var observer := actor(actor_id)
	if observer == null:
		return
	var max_results := clampi(int(command.get("max_results", 32)), 1, 64)
	var observer_zone := _nest.nearest_zone_id(observer.global_position)
	var candidates: Array[String] = []
	for other_actor_id: Variant in _actors.keys():
		var other_id := String(other_actor_id)
		if other_id == actor_id:
			continue
		var other_actor := _actors[other_actor_id] as ElfieActor
		if (
			_nest.nearest_zone_id(other_actor.global_position) == observer_zone
			and observer.global_position.distance_squared_to(
				other_actor.global_position
			) <= VISUAL_MAX_RANGE_SQUARED
		):
			candidates.append("actor/%s" % other_id)
	for anchor_id in SEMANTIC_SCENE_INDEX.sorted_anchor_ids(_nest.semantic_anchor_ids()):
		var marker := _nest.resolve_anchor(anchor_id)
		if marker == null:
			continue
		if (
			_nest.nearest_zone_id(marker.global_position) == observer_zone
			and observer.global_position.distance_squared_to(
				marker.global_position
			) <= VISUAL_MAX_RANGE_SQUARED
		):
			candidates.append("anchor/%s" % anchor_id)
	var manifest := _nest.scene_manifest()
	candidates.append_array(
		SEMANTIC_SCENE_INDEX.active_facility_ids(manifest, observer_zone)
	)
	candidates.sort()
	if candidates.size() > max_results:
		candidates.resize(max_results)
	runtime_event.emit(
		"visual_observation",
		{
			"observation_id": observation_id,
			"actor_id": actor_id,
			"zone_id": observer_zone,
			"visible_semantic_ids": candidates,
		},
		observation_id,
	)


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
			existing.cancel_navigation("actor_removed")
			if not _terminal_commands.has(command_id):
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
	_emit_terminal(command_id, actor_id, status, reason)


func _on_actor_movement_blocked(command_id: String, actor_id: String) -> void:
	runtime_event.emit(
		"movement_blocked",
		{"command_id": command_id, "actor_id": actor_id},
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


func _emit_command_event(
	event_name: String,
	command_id: String,
	actor_id: String,
) -> void:
	runtime_event.emit(
		event_name,
		{"command_id": command_id, "actor_id": actor_id},
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
	if not reason.is_empty():
		payload["reason"] = reason
	runtime_event.emit("intent_terminal", payload, command_id)
