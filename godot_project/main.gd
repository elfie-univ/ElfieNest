extends Node3D

const ACTOR_SCENES := {
	"dog": preload("res://characters/dog/dog.tscn"),
	"fox": preload("res://characters/fox/fox.tscn"),
}
const GODOT_WS_URL := "ws://127.0.0.1:8765"
const GODOT_PROTOCOL_VERSION := 2
const WORLD_RUNTIME_CONTROLLER := preload("res://runtime/world_controller.gd")
const ACTOR_RUNTIME_CONTROLLER := preload("res://runtime/actor_controller.gd")
const RUNTIME_WEBSOCKET_CLIENT := preload("res://runtime/websocket_client.gd")
const RUNTIME_MODE := preload("res://runtime/runtime_mode.gd")
const LAB_RUNTIME := preload("res://runtime/lab_runtime.gd")
const AUTHORITY_SEMANTIC_EVENTS := preload("res://runtime/authority_semantic_events.gd")
const OBSERVER_CHANNEL := "elfienest.observer"
const OBSERVER_PROTOCOL_VERSION := 1
const OBSERVER_MODE_PARAMETER := "observer"
const OBSERVER_MODE_VALUE := "product"

@onready var nest: ModularNest = $Nest
@onready var characters: Node3D = $Characters
@onready var lab_preview: Node3D = $LabPreview
@onready var lab_camera: Camera3D = $LabPreview/Camera3D

var _ws_url := ""
var _lab_mode := false
var _nest_lab_mode := false
var _product_observer_mode := false
var _lab_runtime: Node
var _world_controller: Node
var _actor_controller: Node
var _runtime_client: Node
var _runtime_mode
var _semantic_events
var _observer_window: JavaScriptObject
var _observer_origin := ""


func add_character(
	character_scene: PackedScene,
	spawn_position: Vector3 = Vector3.ZERO,
	install_animations: bool = true,
) -> CharacterBody3D:
	var instance := character_scene.instantiate()
	if not instance is CharacterBody3D:
		instance.queue_free()
		push_error("Character scene root must be CharacterBody3D")
		return null
	var character := instance as CharacterBody3D
	if character is ElfieActor:
		(character as ElfieActor).install_shared_animations = install_animations
	characters.add_child(character)
	character.position = spawn_position
	return character


func _ready() -> void:
	_lab_mode = OS.has_feature("web") and _query_parameter("mode") == "elfie_lab"
	_nest_lab_mode = OS.has_feature("web") and _query_parameter("mode") == "nest_lab"
	_product_observer_mode = (
		OS.has_feature("web")
		and _query_parameter(OBSERVER_MODE_PARAMETER) == OBSERVER_MODE_VALUE
	)
	_setup_lab_runtime()
	if _lab_mode:
		_lab_runtime.setup_elfie_lab()
		return
	if _nest_lab_mode:
		_lab_runtime.setup_nest_lab()
		return
	if _product_observer_mode:
		_enter_product_observer_presentation_mode()
		nest.show_observation_hud = false
		nest.set_observation_hud_visible(false)
		_setup_product_observer_bridge()
		await _notify_web_runtime_ready()
		_publish_observer_catalog()
		return
	_runtime_mode = RUNTIME_MODE.new()
	_runtime_mode.setup(_resolve_runtime_mode())
	if _runtime_mode.disables_visual_runtime_services():
		nest.visible = false
	if not _runtime_mode.allows_authority_transport():
		if _runtime_mode.requires_web_ready_signal():
			await _notify_web_runtime_ready()
		return
	_start_authority_runtime()


func _process(_delta: float) -> void:
	if _lab_mode:
		_lab_runtime.process_elfie_lab_frame()
		return
	if _nest_lab_mode:
		_lab_runtime.process_nest_lab_frame()
		return
	if _product_observer_mode:
		_poll_observer_commands()
		return
	if _runtime_client != null:
		_runtime_client.process_frame()


func _setup_lab_runtime() -> void:
	_lab_runtime = LAB_RUNTIME.new()
	add_child(_lab_runtime)
	_lab_runtime.setup(nest, characters, lab_preview, lab_camera, ACTOR_SCENES)


func _start_authority_runtime() -> void:
	_semantic_events = AUTHORITY_SEMANTIC_EVENTS.new()
	_world_controller = WORLD_RUNTIME_CONTROLLER.new()
	add_child(_world_controller)
	_world_controller.setup(nest)
	_world_controller.runtime_event.connect(_on_runtime_event)
	_actor_controller = ACTOR_RUNTIME_CONTROLLER.new()
	add_child(_actor_controller)
	_actor_controller.setup(nest, characters, ACTOR_SCENES)
	_actor_controller.runtime_event.connect(_on_runtime_event)
	_ws_url = _resolve_runtime_ws_url()
	_runtime_client = RUNTIME_WEBSOCKET_CLIENT.new()
	add_child(_runtime_client)
	_runtime_client.command_message.connect(_handle_runtime_command)
	_runtime_client.setup(_ws_url, _resolve_handshake_nonce())


func _handle_runtime_command(message: Dictionary) -> void:
	var command_name := String(message.get("name", ""))
	var payload: Variant = message.get("payload", {})
	if not payload is Dictionary or not _runtime_command_is_valid(
		message,
		command_name,
		payload as Dictionary,
	):
		return
	match command_name:
		"configure_world":
			await _world_controller.configure_world(
				payload as Dictionary,
				String(message.get("message_id", "")),
			)
		"sync_actors":
			var result: Dictionary = _actor_controller.sync_actors(
				(payload as Dictionary).get("actors", []),
			)
			if bool(result.get("accepted", false)):
				_send_runtime_event(
					"world_snapshot",
					result.get("snapshot", {}) as Dictionary,
					String(message.get("message_id", "")),
				)
			else:
				_send_runtime_event(
					"startup_error",
					result,
					String(message.get("message_id", "")),
				)
		"execute_intent":
			_actor_controller.execute_intent(payload as Dictionary)
		"cancel_intent":
			_actor_controller.cancel_intent(payload as Dictionary)
		_:
			return


func _runtime_command_is_valid(
	message: Dictionary,
	command_name: String,
	payload: Dictionary,
) -> bool:
	if (
		int(message.get("protocol", 0)) != GODOT_PROTOCOL_VERSION
		or String(message.get("runtime_id", "")) != String(_runtime_client.runtime_id)
		or int(message.get("generation", -1)) != int(_runtime_client.runtime_generation)
		or String(message.get("message_id", "")).is_empty()
	):
		return false
	var revision := int(message.get("world_revision", -1))
	if command_name != "configure_world" and revision != nest.world_revision:
		return false
	if command_name in ["execute_intent", "cancel_intent"]:
		var command_id := String(payload.get("command_id", ""))
		if command_id.is_empty() or String(message.get("correlation_id", "")) != command_id:
			return false
	return true


func _on_runtime_event(
	event_name: String,
	payload: Dictionary,
	correlation_id: String,
) -> void:
	var semantic_event: Dictionary = _semantic_events.project(
		event_name,
		payload,
		correlation_id,
	)
	_send_runtime_event(
		String(semantic_event["name"]),
		semantic_event["payload"] as Dictionary,
		String(semantic_event.get("correlation_id", "")),
	)


func _resolve_handshake_nonce() -> String:
	var environment_nonce := OS.get_environment("ELFIENEST_GODOT_NONCE")
	if not environment_nonce.is_empty():
		return environment_nonce
	if not OS.has_feature("web"):
		return ""
	return _query_parameter("nonce")


func _resolve_runtime_mode() -> String:
	var environment_mode := OS.get_environment("ELFIENEST_GODOT_MODE")
	if not environment_mode.is_empty():
		return environment_mode
	if OS.has_feature("dedicated_server") or DisplayServer.get_name() == "headless":
		return "authority"
	if OS.has_feature("web"):
		return _query_parameter("mode")
	return "authority"


func _resolve_runtime_ws_url() -> String:
	var environment_url := OS.get_environment("ELFIENEST_GODOT_WS")
	if not environment_url.is_empty():
		return environment_url
	if OS.has_feature("web"):
		var query_url := _query_parameter("ws")
		if _is_loopback_websocket_url(query_url):
			return query_url
	return GODOT_WS_URL


func _is_loopback_websocket_url(value: String) -> bool:
	var normalized := value.strip_edges()
	if not normalized.begins_with("ws://") or normalized.find("@") != -1:
		return false
	var authority := normalized.trim_prefix("ws://")
	if authority.contains("/") or authority.contains("?") or authority.contains("#"):
		return false
	var separator := authority.rfind(":")
	if separator <= 0:
		return false
	var hostname := authority.left(separator).to_lower()
	var port := authority.substr(separator + 1)
	if hostname not in ["127.0.0.1", "localhost"] or not port.is_valid_int():
		return false
	var port_number := int(port)
	return port_number >= 1 and port_number <= 65535


func _setup_product_observer_bridge() -> void:
	if not OS.has_feature("web"):
		return
	_observer_window = JavaScriptBridge.get_interface("window")
	if _observer_window == null:
		return
	_observer_origin = String(_observer_window.location.origin)
	nest.observer_camera_catalog_changed.connect(_on_observer_camera_catalog_changed)
	JavaScriptBridge.eval(
		"(() => { window.__elfieNestObserverQueue = [];"
		+ " window.addEventListener('message', (event) => {"
		+ " if (event.origin !== window.location.origin) return;"
		+ " if (event.source !== window.parent) return;"
		+ " const data = event.data;"
		+ " if (data && data.channel === 'elfienest.observer'"
		+ " && data.version === 1 && data.kind === 'camera_command')"
		+ " window.__elfieNestObserverQueue.push(JSON.stringify(data));"
		+ " }); })()"
	)


func _enter_product_observer_presentation_mode() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


func _poll_observer_commands() -> void:
	if not OS.has_feature("web"):
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
				var command := _parse_observer_command(parsed_message as Dictionary)
				if not command.is_empty():
					_handle_observer_command(command)


func _accepts_observer_message(message: Dictionary) -> bool:
	if typeof(message.get("channel")) != TYPE_STRING:
		return false
	if message["channel"] != OBSERVER_CHANNEL:
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
	if typeof(message.get("kind")) != TYPE_STRING:
		return false
	if message["kind"] != "camera_command":
		return false
	if typeof(message.get("action")) != TYPE_STRING:
		return false
	var action := message["action"] as String
	match action:
		"overview":
			return _observer_message_has_exact_keys(message, [])
		"select":
			return _observer_message_has_exact_keys(message, ["view_id"])
		"reset":
			return _observer_message_has_exact_keys(message, [])
		"set_local_presentation_paused":
			return _observer_message_has_exact_keys(message, ["paused"])
		_:
			return false


func _observer_message_has_exact_keys(message: Dictionary, optional_keys: Array) -> bool:
	var allowed_keys := ["channel", "version", "kind", "action"]
	allowed_keys.append_array(optional_keys)
	if message.keys().size() != allowed_keys.size():
		return false
	for key: Variant in message.keys():
		if typeof(key) != TYPE_STRING:
			return false
		if key not in allowed_keys:
			return false
	return true


func _parse_observer_command(message: Dictionary) -> Dictionary:
	if not _product_observer_mode or not _accepts_observer_message(message):
		return {}
	var action := message["action"] as String
	match action:
		"overview":
			return {"action": action}
		"select":
			if typeof(message.get("view_id")) != TYPE_STRING:
				return {}
			var view_id := message["view_id"] as String
			if view_id.is_empty():
				return {}
			return {"action": action, "view_id": view_id}
		"reset":
			return {"action": action}
		"set_local_presentation_paused":
			if not message.get("paused") is bool:
				return {}
			return {"action": action, "paused": bool(message["paused"])}
		_:
			return {}


func _handle_observer_command(command: Dictionary) -> void:
	match String(command["action"]):
		"overview":
			nest.select_observer_overview()
		"select":
			nest.select_observer_camera_by_id(String(command["view_id"]))
		"reset":
			nest.reset_observer_camera()
		"set_local_presentation_paused":
			_set_local_observer_presentation_paused(bool(command["paused"]))
		_:
			return


func _set_local_observer_presentation_paused(paused: bool) -> void:
	nest.set_observer_presentation_paused(paused)
	if is_inside_tree():
		get_tree().paused = paused


func _on_observer_camera_catalog_changed(_catalog: Dictionary) -> void:
	_publish_observer_catalog()


func _publish_observer_catalog() -> void:
	if _observer_window == null:
		return
	var catalog := nest.observer_camera_catalog().merged({
		"channel": OBSERVER_CHANNEL,
		"version": OBSERVER_PROTOCOL_VERSION,
		"kind": "camera_catalog",
	})
	_observer_window.parent.postMessage(JSON.stringify(catalog), _observer_origin)


func _query_parameter(name: String) -> String:
	var query: Variant = JavaScriptBridge.eval("window.location.search")
	if not query is String:
		return ""
	for part in String(query).trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2 and pair[0] == name:
			return String(pair[1]).uri_decode()
	return ""


func _send_runtime_event(event_name: String, payload: Dictionary, correlation_id: String = "") -> void:
	_runtime_client.send_runtime_event(
		event_name,
		payload,
		nest.world_revision,
		correlation_id,
	)


func _notify_web_runtime_ready() -> void:
	"""Emit the existing iframe readiness contract for observer-only Web modes."""
	if not OS.has_feature("web"):
		return
	for _frame in range(4):
		await get_tree().process_frame
	var window := JavaScriptBridge.get_interface("window")
	if window == null:
		return
	window.parent.postMessage("elfienest:godot-web-ready", window.location.origin)
