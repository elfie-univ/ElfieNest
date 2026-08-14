extends RefCounted

const HOST_LOCAL_FIELDS := ["host", "occurred_at", "process_id", "runtime_id", "timestamp"]

var _events: Array[Dictionary] = []


func project(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
) -> Dictionary:
	"""Project a runtime signal into host-independent semantic facts."""
	return _append(event_name, payload, cause_id)


func record(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
) -> Dictionary:
	"""Record the same projection used by the authority transport boundary."""
	return _append(event_name, payload, cause_id)


func events() -> Array[Dictionary]:
	"""Return the ordered semantic projection without mutable host state."""
	return _events.duplicate(true)


func _append(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
) -> Dictionary:
	var event := {
		"sequence": _events.size() + 1,
		"name": event_name,
		"payload": _semantic_payload(payload),
	}
	if not cause_id.is_empty():
		event["cause_id"] = cause_id
	_events.append(event)
	return event


func _semantic_payload(payload: Dictionary) -> Dictionary:
	var semantic_payload := {}
	for key: Variant in payload:
		if String(key) not in HOST_LOCAL_FIELDS:
			semantic_payload[key] = payload[key]
	return semantic_payload
