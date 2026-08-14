class_name ElfieNestRuntimeMode
extends RefCounted

const AUTHORITY := "authority"
const OBSERVER_ROOM := "observer_room"
const OBSERVER_ELFIE := "observer_elfie"
const DISABLED := "disabled"

var _name := AUTHORITY


func setup(raw_mode: String) -> void:
	"""Accept only explicit runtime roles; all other values fail closed."""
	match raw_mode:
		AUTHORITY, OBSERVER_ROOM, OBSERVER_ELFIE:
			_name = raw_mode
		_:
			_name = DISABLED


func allows_authority_transport(is_lab_runtime: bool = false) -> bool:
	return not is_lab_runtime and _name == AUTHORITY


func disables_visual_runtime_services() -> bool:
	return _name == AUTHORITY


func requires_web_ready_signal() -> bool:
	"""Keep observer Web embeds compatible without granting authority transport."""
	return _name == OBSERVER_ROOM or _name == OBSERVER_ELFIE


func name() -> String:
	return _name
