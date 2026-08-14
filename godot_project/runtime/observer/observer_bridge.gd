class_name NestObserverBridge
extends Node

const OBSERVER_CHANNEL := "elfienest.observer"
const OBSERVER_PROTOCOL_VERSION := 1

var _nest: ModularNest
var _presentation: Node
var _enabled := false
var _observer_window: JavaScriptObject
var _observer_origin := ""


func setup(nest: ModularNest, presentation: Node, enabled: bool) -> void:
	_nest = nest
	_presentation = presentation
	_enabled = enabled


func setup_web_bridge() -> void:
	if not _enabled or not OS.has_feature("web"):
		return
	_observer_window = JavaScriptBridge.get_interface("window")
	if _observer_window == null:
		return
	_observer_origin = String(_observer_window.location.origin)
	_nest.observer_camera_catalog_changed.connect(_on_camera_catalog_changed)
	JavaScriptBridge.eval(
		"(() => { window.__elfieNestObserverQueue = [];"
		+ " window.addEventListener('message', (event) => {"
		+ " if (event.origin !== window.location.origin) return;"
		+ " if (event.source !== window.parent) return;"
		+ " const data = event.data;"
		+ " if (data && data.channel === 'elfienest.observer'"
		+ " && data.version === 1"
		+ " && (data.kind === 'camera_command' || data.kind === 'semantic_snapshot' || data.kind === 'world_config'))"
		+ " window.__elfieNestObserverQueue.push(JSON.stringify(data));"
		+ " }); })()"
	)


func process_frame() -> void:
	if not _enabled or not OS.has_feature("web"):
		return
	var raw_batch: Variant = JavaScriptBridge.eval(
		"window.__elfieNestObserverQueue && window.__elfieNestObserverQueue.length"
		+ " ? JSON.stringify(window.__elfieNestObserverQueue.splice(0)) : ''"
	)
	if not raw_batch is String or String(raw_batch).is_empty():
		return
	var parsed_batch: Variant = JSON.parse_string(String(raw_batch))
	if not parsed_batch is Array:
		return
	for raw_message: Variant in parsed_batch as Array:
		if raw_message is String:
			var parsed_message: Variant = JSON.parse_string(String(raw_message))
			if parsed_message is Dictionary:
				var world_config := _parse_world_config(parsed_message as Dictionary)
				if not world_config.is_empty():
					_nest.apply_observer_world_config(world_config)
					continue
				var semantic_snapshot := _parse_semantic_snapshot(parsed_message as Dictionary)
				if not semantic_snapshot.is_empty():
					_handle_semantic_snapshot(semantic_snapshot)
					continue
				var command := _parse_camera_command(parsed_message as Dictionary)
				if not command.is_empty():
					_handle_camera_command(command)


func publish_catalog() -> void:
	if _observer_window == null:
		return
	var catalog := _nest.observer_camera_catalog().merged({
		"channel": OBSERVER_CHANNEL,
		"version": OBSERVER_PROTOCOL_VERSION,
		"kind": "camera_catalog",
	})
	_observer_window.parent.postMessage(JSON.stringify(catalog), _observer_origin)


func _parse_world_config(message: Dictionary) -> Dictionary:
	if not _enabled or not _has_exact_keys(message, ["channel", "version", "kind", "nest_id", "bed_count"]):
		return {}
	if (
		typeof(message.get("channel")) != TYPE_STRING
		or String(message["channel"]) != OBSERVER_CHANNEL
		or _parse_revision(message.get("version")) != OBSERVER_PROTOCOL_VERSION
		or typeof(message.get("kind")) != TYPE_STRING
		or String(message["kind"]) != "world_config"
		or typeof(message.get("nest_id")) != TYPE_STRING
		or String(message["nest_id"]).is_empty()
	):
		return {}
	var bed_count := _parse_revision(message.get("bed_count"))
	if bed_count < 4 or bed_count > 32:
		return {}
	return {"nest_id": String(message["nest_id"]), "bed_count": bed_count}


func _parse_semantic_snapshot(message: Dictionary) -> Dictionary:
	if not _enabled or not _has_exact_keys(
		message,
		[
			"channel",
			"version",
			"kind",
			"protocol",
			"generation",
			"sequence",
			"scope",
			"entities",
			"entity_revisions",
		],
	):
		return {}
	if (
		typeof(message.get("channel")) != TYPE_STRING
		or String(message["channel"]) != OBSERVER_CHANNEL
		or typeof(message.get("kind")) != TYPE_STRING
		or String(message["kind"]) != "semantic_snapshot"
		or _parse_revision(message["version"]) != OBSERVER_PROTOCOL_VERSION
		or _parse_revision(message["protocol"]) != 3
		or _parse_revision(message["generation"]) < 1
		or _parse_revision(message["sequence"]) < 1
	):
		return {}
	var scope: Variant = message.get("scope")
	if not _semantic_scope_is_valid(scope):
		return {}
	var entities: Variant = message.get("entities")
	var revisions: Variant = message.get("entity_revisions")
	if not entities is Dictionary or not revisions is Dictionary:
		return {}
	if _has_forbidden_keys(message):
		return {}
	var entity_map := entities as Dictionary
	var revision_map := revisions as Dictionary
	if entity_map.keys().size() != revision_map.keys().size():
		return {}
	for raw_id: Variant in entity_map.keys():
		if typeof(raw_id) != TYPE_STRING or String(raw_id).is_empty():
			return {}
		if not revision_map.has(raw_id) or _parse_revision(revision_map[raw_id]) < 1:
			return {}
		if not _semantic_entity_is_valid(entity_map[raw_id]):
			return {}
	return message


func _semantic_scope_is_valid(scope: Variant) -> bool:
	if not scope is Dictionary:
		return false
	var scope_map := scope as Dictionary
	var kind := String(scope_map.get("kind", ""))
	if kind == "room":
		return (
			_has_exact_keys(scope_map, ["kind", "room_id"])
			and _text_is_valid(scope_map.get("room_id"))
		)
	if kind == "elfie":
		return (
			_has_exact_keys(scope_map, ["kind", "elfie_id"])
			and _text_is_valid(scope_map.get("elfie_id"))
		)
	return false


func _semantic_entity_is_valid(entity: Variant) -> bool:
	if not entity is Dictionary:
		return false
	var entity_map := entity as Dictionary
	if not _has_exact_keys(
		entity_map,
		[
			"room_id",
			"zone_id",
			"posture",
			"active",
			"active_command_id",
			"species_id",
			"appearance",
			"home_anchor_id",
		],
	):
		return false
	return (
		_text_is_valid(entity_map.get("room_id"))
		and _text_or_null_is_valid(entity_map.get("zone_id"))
		and _text_is_valid(entity_map.get("posture"))
		and typeof(entity_map.get("active")) == TYPE_BOOL
		and _text_or_null_is_valid(entity_map.get("active_command_id"))
		and _text_or_null_is_valid(entity_map.get("species_id"))
		and entity_map.get("appearance") is Dictionary
		and _text_or_null_is_valid(entity_map.get("home_anchor_id"))
	)


func _accepts_camera_command(message: Dictionary) -> bool:
	if typeof(message.get("channel")) != TYPE_STRING or message["channel"] != OBSERVER_CHANNEL:
		return false
	var version: Variant = message.get("version")
	if typeof(version) == TYPE_INT:
		if version != OBSERVER_PROTOCOL_VERSION:
			return false
	elif typeof(version) == TYPE_FLOAT:
		if version != float(OBSERVER_PROTOCOL_VERSION):
			return false
	else:
		return false
	if typeof(message.get("kind")) != TYPE_STRING or message["kind"] != "camera_command":
		return false
	if typeof(message.get("action")) != TYPE_STRING:
		return false
	var action := message["action"] as String
	match action:
		"overview":
			return _has_exact_keys(message, ["channel", "version", "kind", "action"])
		"reset":
			return _has_exact_keys(message, ["channel", "version", "kind", "action"])
		"select":
			return _has_exact_keys(message, ["channel", "version", "kind", "action", "view_id"])
		"set_local_presentation_paused":
			return _has_exact_keys(message, ["channel", "version", "kind", "action", "paused"])
		_:
			return false


func _parse_camera_command(message: Dictionary) -> Dictionary:
	if not _enabled or not _accepts_camera_command(message):
		return {}
	var action := message["action"] as String
	match action:
		"overview":
			return {"action": action}
		"reset":
			return {"action": action}
		"select":
			if typeof(message.get("view_id")) != TYPE_STRING or String(message["view_id"]).is_empty():
				return {}
			return {"action": action, "view_id": String(message["view_id"])}
		"set_local_presentation_paused":
			if not message.get("paused") is bool:
				return {}
			return {"action": action, "paused": bool(message["paused"])}
		_:
			return {}


func _handle_camera_command(command: Dictionary) -> void:
	match String(command["action"]):
		"overview":
			_nest.select_observer_overview()
		"select":
			_nest.select_observer_camera_by_id(String(command["view_id"]))
		"reset":
			_nest.reset_observer_camera()
		"set_local_presentation_paused":
			_set_local_presentation_paused(bool(command["paused"]))
		_:
			return


func _set_local_presentation_paused(paused: bool) -> void:
	_nest.set_observer_presentation_paused(paused)
	if is_inside_tree():
		get_tree().paused = paused


func _handle_semantic_snapshot(snapshot: Dictionary) -> void:
	if _presentation != null:
		_presentation.apply_snapshot(snapshot)


func _on_camera_catalog_changed(_catalog: Dictionary) -> void:
	publish_catalog()


func _parse_revision(value: Variant) -> int:
	if typeof(value) == TYPE_INT:
		return int(value)
	if typeof(value) == TYPE_FLOAT and is_equal_approx(float(value), roundf(float(value))):
		return roundi(float(value))
	return -1


func _text_is_valid(value: Variant) -> bool:
	return typeof(value) == TYPE_STRING and not String(value).is_empty()


func _text_or_null_is_valid(value: Variant) -> bool:
	return value == null or _text_is_valid(value)


func _has_exact_keys(value: Dictionary, expected_keys: Array) -> bool:
	if value.keys().size() != expected_keys.size():
		return false
	for key: Variant in value.keys():
		if typeof(key) != TYPE_STRING:
			return false
		if key not in expected_keys:
			return false
	return true


func _has_forbidden_keys(value: Variant) -> bool:
	if value is Array:
		for nested: Variant in value as Array:
			if _has_forbidden_keys(nested):
				return true
		return false
	if not value is Dictionary:
		return false
	for raw_key: Variant in (value as Dictionary).keys():
		if String(raw_key) in [
			"x", "y", "z", "position", "positions", "transform", "transforms",
			"coordinates", "fov", "frame", "frames", "credential", "credentials",
			"token", "nonce", "authority",
		]:
			return true
		if _has_forbidden_keys((value as Dictionary)[raw_key]):
			return true
	return false
