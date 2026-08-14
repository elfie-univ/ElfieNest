class_name NestAuthorityEndpoint
extends RefCounted

const PROTOCOL_VERSION := 3
const ENVIRONMENT_OBJECT_ID := "nest/environment"

## Validate the typed command envelope before dispatching to a capability owner.
## This is the Godot endpoint boundary; it does not execute world or Body work.
func validate_command(
	message: Dictionary,
	command_name: String,
	payload: Dictionary,
	runtime_id: String,
	runtime_generation: int,
	world_revision: int,
) -> bool:
	if (
		int(message.get("protocol", 0)) != PROTOCOL_VERSION
		or String(message.get("runtime_id", "")) != runtime_id
		or int(message.get("generation", -1)) != runtime_generation
		or String(message.get("message_id", "")).is_empty()
	):
		return false
	var revision := int(message.get("world_revision", -1))
	if command_name != "configure_world" and revision != world_revision:
		return false
	var is_body_command := command_name in ["execute_intent", "cancel_intent"]
	var expected_lane := "body" if is_body_command else "nest"
	if String(message.get("lane", "")) != expected_lane:
		return false
	if command_name in ["execute_intent", "cancel_intent"]:
		var command_id := String(payload.get("command_id", ""))
		var actor_id := String(payload.get("actor_id", ""))
		if (
			command_id.is_empty()
			or actor_id.is_empty()
			or String(message.get("cause_id", "")) != command_id
			or String(message.get("target_actor_id", "")) != actor_id
		):
			return false
	elif command_name == "request_speech_reach":
		var speech_command_id := String(payload.get("command_id", ""))
		var speech_actor_id := String(payload.get("actor_id", ""))
		if (
			speech_command_id.is_empty()
			or speech_actor_id.is_empty()
			or String(message.get("cause_id", "")) != speech_command_id
		):
			return false
		if _has_target_actor_id(message):
			return false
	elif command_name == "request_visual_observation":
		var observation_id := String(payload.get("observation_id", ""))
		var observation_actor_id := String(payload.get("actor_id", ""))
		var max_results := int(payload.get("max_results", 0))
		if (
			observation_id.is_empty()
			or observation_actor_id.is_empty()
			or max_results < 1
			or max_results > 64
			or String(message.get("cause_id", "")) != observation_id
		):
			return false
		if _has_target_actor_id(message):
			return false
	elif command_name == "apply_environment":
		var environment_command_id := String(payload.get("command_id", ""))
		var environment_object_id := String(payload.get("object_id", ""))
		if (
			environment_object_id != ENVIRONMENT_OBJECT_ID
			or environment_command_id.is_empty()
			or typeof(payload.get("lights_on")) != TYPE_BOOL
			or typeof(payload.get("quiet_mode")) != TYPE_BOOL
			or String(message.get("cause_id", "")) != environment_command_id
		):
			return false
		if _has_target_actor_id(message):
			return false
	elif _has_target_actor_id(message):
		return false
	return true


func _has_target_actor_id(message: Dictionary) -> bool:
	var target: Variant = message.get("target_actor_id", null)
	return target != null and not String(target).is_empty()
