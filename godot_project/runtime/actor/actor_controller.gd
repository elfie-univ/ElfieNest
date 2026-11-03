class_name NestActorRuntimeController
extends Node

const ACTOR_CATALOG := preload("res://runtime/actor/actor_catalog.gd")
const ARRIVAL := preload("res://runtime/actor/adoption_arrival.gd")

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
var preview_demonstrations: Node
var _preview_switches: Dictionary = {}

func home_anchor_for(actor_id: String) -> String:
	var data: Variant = JSON.parse_string(str(_actor_catalog.get(actor_id,"{}")))
	return str(data.get("spawn_anchor_id", "")) if data is Dictionary else ""
var _command_actor_ids: Dictionary = {}
var _command_metadata: Dictionary = {}
var _terminal_commands: Dictionary = {}
var _pending_anchor_uses: Dictionary = {}
var _install_actor_animations := true
var _arrival_path: RefCounted
var _arrivals: Dictionary = {}


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
		if _actors.has(actor_id):
			var prior: Dictionary = JSON.parse_string(String(_actor_catalog[actor_id]))
			if prior["species"] == actor_data["species"] and prior["appearance"] == actor_data["appearance"] and prior["spawn_anchor_id"] == actor_data["spawn_anchor_id"]:
				_actor_catalog[actor_id] = fingerprint
				_apply_resident_lifecycle(_actors[actor_id], actor_data)
				continue
		_remove_actor(actor_id)
		var actor := _create_actor(actor_data)
		if actor == null:
			return {"accepted": false, "code": "actor_instantiation_failed"}
		_actors[actor_id] = actor
		_actor_catalog[actor_id] = fingerprint
		_apply_resident_lifecycle(actor, actor_data)

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


func _apply_resident_lifecycle(body: ElfieActor, data: Dictionary) -> void:
	var hosted := bool(data.get("hosted", false))
	var was_hosted := bool(body.get_meta("hosted", false))
	body.set_meta("hosted", hosted)
	if hosted:
		_arrivals.erase(body.elfie_id)
		if not body.active_command_id.is_empty(): body.cancel_navigation("hosted")
		if body.furniture_anchor_id.is_empty():
			var bed := _nest.resolve_anchor(String(data["spawn_anchor_id"]))
			body.global_position = bed.global_position
			body.enter_furniture(bed, String(data["spawn_anchor_id"]))
		body.set_physics_process(false)
		return
	if was_hosted:
		body.leave_furniture()
		body.set_physics_process(true)
	var started: Variant = data.get("arrival_started_at")
	if started == null or Time.get_unix_time_from_system() - float(started) >= ARRIVAL.TIMING.SETTLED_AT:
		body.set_meta("arrival_completed", true)
		return
	if _arrival_path == null:
		var path := ARRIVAL.new()
		if not path.bind(_nest):
			body.set_meta("arrival_completed", false)
			push_error("Adoption arrival requires actual fourth-floor platform colliders")
			return
		_arrival_path = path
	body.set_meta("arrival_completed", false)
	body.set_physics_process(false)
	_arrivals[body.elfie_id] = float(started)
	_process(0.0)


func _process(_delta: float) -> void:
	for actor_id: String in _arrivals.keys():
		var body := actor(actor_id)
		if body == null:
			_arrivals.erase(actor_id)
			continue
		var elapsed := Time.get_unix_time_from_system() - float(_arrivals[actor_id])
		_arrival_path.call("sample", body, elapsed)
		if elapsed >= ARRIVAL.TIMING.SETTLED_AT:
			_arrivals.erase(actor_id)
			body.set_meta("arrival_completed", true)
			body.set_meta("action_anchor_id", "central-04/activity")
			body.set_physics_process(true)


func world_snapshot() -> Dictionary:
	return ACTOR_CATALOG.snapshot(_nest, _actors, _actor_catalog)

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
	var raw_generation: Variant = command.get("body_generation", 1)
	var body_generation := 1
	if typeof(raw_generation) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(raw_generation)):
		body_generation = maxi(int(raw_generation), 1)
	_command_metadata[command_id] = {
		"intent_id": String(command.get("intent_id", command_id)),
		"body_generation": body_generation,
	}
	_emit_command_event("intent_accepted", command_id, actor_id)
	if preview_demonstrations != null and not command_id.begins_with("demo-") and preview_demonstrations.running(actor_id):
		var prior := str(_preview_switches.get(actor_id,""))
		if not prior.is_empty(): _emit_terminal(prior, actor_id, "cancelled", "superseded_before_start")
		_preview_switches[actor_id] = command_id
		preview_demonstrations.cancel(actor_id)
		while preview_demonstrations.running(actor_id): await get_tree().physics_frame
		if _preview_switches.get(actor_id) != command_id: return
		_preview_switches.erase(actor_id)
	var actor_instance := actor(actor_id)
	if actor_instance == null:
		_emit_terminal(command_id, actor_id, "failed", "actor_not_found")
		return
	if actor_instance.has_method("play_furniture_cycle") and not str(actor_instance.get("furniture_cycle_command")).is_empty():
		_emit_terminal(command_id, actor_id, "failed", "actor_busy")
		return
	if bool(actor_instance.get_meta("hosted", false)) or not bool(actor_instance.get_meta("arrival_completed", true)):
		_emit_terminal(command_id, actor_id, "failed", "virtual_body_unavailable")
		return
	var intent := String(command.get("intent", ""))
	if intent == "use_anchor":
		_execute_use_anchor(command, actor_instance)
		return
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
	actor_instance.set_meta("action_anchor_id", anchor_id)
	_emit_command_event("intent_started", command_id, actor_id)


func cancel_intent(command: Dictionary) -> void:
	var command_id := String(command.get("command_id", ""))
	var actor_id := String(_command_actor_ids.get(command_id, ""))
	if actor_id.is_empty() or _terminal_commands.has(command_id):
		return
	if _preview_switches.get(actor_id) == command_id:
		_preview_switches.erase(actor_id)
		_emit_terminal(command_id, actor_id, "cancelled", "cancelled_before_start")
		return
	var actor_instance := actor(actor_id)
	if actor_instance != null and actor_instance.has_method("play_furniture_cycle") and str(actor_instance.get("furniture_cycle_command")) == command_id:
		actor_instance.call("cancel_furniture_cycle", "cancelled_by_controller")
		return
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
	actor.set_meta("action_anchor_id", String(actor_data["spawn_anchor_id"]))
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
	_arrivals.erase(actor_id)
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


var _cycle_requests: Dictionary = {}

func _on_actor_navigation_terminal(
	command_id: String,
	status: String,
	reason: String,
	actor_id: String,
) -> void:
	if _pending_anchor_uses.has(command_id):
		var anchor_id := String(_pending_anchor_uses[command_id])
		if status == "completed" and _cycle_requests.has(command_id):
			var body := actor(actor_id)
			var variant := str(_cycle_requests[command_id])
			_cycle_requests.erase(command_id)
			if body != null and body.has_method("play_furniture_cycle"):
				var result: Dictionary = await body.play_furniture_cycle(_nest.resolve_anchor(anchor_id), anchor_id, command_id, variant, _nest)
				_pending_anchor_uses.erase(command_id)
				_emit_terminal(command_id, actor_id, str(result.status), str(result.reason))
				return
		_pending_anchor_uses.erase(command_id)
		_cycle_requests.erase(command_id)
		if status == "completed":
			var actor_instance := actor(actor_id)
			var marker := _nest.resolve_anchor(anchor_id)
			var error := "actor_not_found"
			if actor_instance != null:
				error = actor_instance.enter_furniture(marker, anchor_id)
			if not error.is_empty():
				_emit_terminal(command_id, actor_id, "failed", error)
				return
	_emit_terminal(command_id, actor_id, status, reason)


func _execute_use_anchor(command: Dictionary, actor_instance: ElfieActor) -> void:
	var command_id := String(command["command_id"])
	var actor_id := String(command["actor_id"])
	if not _valid_use_anchor_payload(command):
		_emit_terminal(command_id, actor_id, "failed", "invalid_use_anchor_payload")
		return
	var anchor_id := String(command["anchor_id"])
	var marker := _nest.resolve_anchor(anchor_id)
	var marker_error := ElfieActor.furniture_marker_error(marker)
	if not marker_error.is_empty():
		_emit_terminal(command_id, actor_id, "failed", marker_error)
		return
	for other: Variant in _actors.values():
		if other != actor_instance and (other as ElfieActor).furniture_anchor_id == anchor_id:
			_emit_terminal(command_id, actor_id, "failed", "furniture_occupied")
			return
	if _pending_anchor_uses.values().has(anchor_id):
		_emit_terminal(command_id, actor_id, "failed", "furniture_occupied")
		return
	if bool(_nest.get_meta("lab_action_preview", false)):
		if not actor_instance.leave_furniture():
			_emit_terminal(command_id, actor_id, "failed", "preview_exit_blocked")
			return
		# The Runtime's semantic anchor is already the validated approach point.
		# Keep all coordinates and furniture contact motion in this authority.
		actor_instance.global_position = marker.global_position
		actor_instance.velocity = Vector3.ZERO
	if command.has("furniture_cycle"):
		_cycle_requests[command_id] = command["furniture_cycle"]
		actor_instance.set_meta("furniture_cycle_deadline", Time.get_ticks_msec() + int(float(command["deadline_seconds"])*1000.0))
	_pending_anchor_uses[command_id] = anchor_id
	if bool(_nest.get_meta("lab_action_preview", false)) and command.has("furniture_cycle"):
		# The inspection already placed the actor at this fixture. Start the
		# production cycle directly; its docking and root motion keep collisions.
		actor_instance.set_meta("action_anchor_id", anchor_id)
		_emit_command_event("intent_started", command_id, actor_id)
		var result: Dictionary = await actor_instance.play_furniture_cycle(marker, anchor_id, command_id, str(command["furniture_cycle"]), _nest)
		_cycle_requests.erase(command_id)
		_pending_anchor_uses.erase(command_id)
		_emit_terminal(command_id, actor_id, str(result.status), str(result.reason))
		return
	if not actor_instance.move_to(
		command_id, marker.global_position, float(command["deadline_seconds"]),
	):
		_pending_anchor_uses.erase(command_id)
		_emit_terminal(command_id, actor_id, "failed", "navigation_unavailable_or_actor_busy")
		return
	actor_instance.set_meta("action_anchor_id", anchor_id)
	_emit_command_event("intent_started", command_id, actor_id)


func _valid_use_anchor_payload(command: Dictionary) -> bool:
	var text_fields := [
		"command_id", "intent_id", "actor_id", "initiator", "intent", "anchor_id",
	]
	var cycle := str(command.get("furniture_cycle", ""))
	if command.has("furniture_cycle") and cycle not in ["seat", "sleep-back", "sleep-left", "sleep-right"]: return false
	if command.size() != text_fields.size() + (3 if not cycle.is_empty() else 2):
		return false
	for key: String in text_fields:
		if not command.get(key) is String or String(command[key]).strip_edges().is_empty():
			return false
	var deadline: Variant = command.get("deadline_seconds")
	var generation: Variant = command.get("body_generation")
	return (
		command["initiator"] == "elfie" and command["intent"] == "use_anchor"
		# JSON.parse_string represents JSON integers as floats too.
		and typeof(generation) in [TYPE_FLOAT, TYPE_INT]
		and is_finite(float(generation)) and float(generation) >= 1.0
		and float(generation) == floorf(float(generation))
		and typeof(deadline) in [TYPE_FLOAT, TYPE_INT]
		and is_finite(float(deadline)) and float(deadline) > 0.0
	)


func _on_actor_movement_blocked(command_id: String, actor_id: String) -> void:
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
	actor_instance.set_meta("action_anchor_id", "")
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
	if not actor_instance.leave_furniture():
		_emit_terminal(command_id, actor_id, "failed", "furniture_exit_blocked")
		return
	actor_instance.set_meta("action_anchor_id", "")
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
	if event_name == "intent_started":
		runtime_event.emit("world_snapshot", world_snapshot(), command_id)


func _emit_terminal(
	command_id: String,
	actor_id: String,
	status: String,
	reason: String,
) -> void:
	if _terminal_commands.has(command_id):
		return
	_terminal_commands[command_id] = true
	_cycle_requests.erase(command_id)
	_pending_anchor_uses.erase(command_id)
	var actor_instance := actor(actor_id)
	if status != "completed" and actor_instance != null and (actor_instance.active_command_id.is_empty() or actor_instance.active_command_id == command_id):
		actor_instance.set_meta("action_anchor_id", "")
	var payload := {
		"command_id": command_id,
		"actor_id": actor_id,
		"status": status,
	}
	payload.merge(_command_metadata.get(command_id, {}))
	if not reason.is_empty():
		payload["reason"] = reason
	runtime_event.emit("intent_terminal", payload, command_id)
	runtime_event.emit("world_snapshot", world_snapshot(), command_id)
