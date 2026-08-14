class_name NestEnvironmentRuntimeController
extends Node

signal runtime_event(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
)

var _nest: ModularNest
var _commands: Dictionary = {}


func setup(nest: ModularNest) -> void:
	_nest = nest


func apply_environment(command: Dictionary) -> void:
	var command_id := String(command.get("command_id", ""))
	if command_id.is_empty() or _commands.has(command_id):
		return
	_commands[command_id] = true
	var lights_on := bool(command.get("lights_on", true))
	var quiet_mode := bool(command.get("quiet_mode", false))
	var applied := _nest.apply_environment_state(lights_on, quiet_mode)
	runtime_event.emit(
		"environment_state",
		{
			"command_id": command_id,
			"lights_on": bool(applied.get("lights_on", lights_on)),
			"quiet_mode": bool(applied.get("quiet_mode", quiet_mode)),
			"applied": bool(applied.get("applied", false)),
			"reason": applied.get("reason"),
		},
		command_id,
	)
