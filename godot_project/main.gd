extends Node3D

const ACTOR_SCENES := {
	"dog": preload("res://characters/dog/dog.tscn"),
	"fox": preload("res://characters/fox/fox.tscn"),
}
const GODOT_WS_URL := "ws://127.0.0.1:8765"
const GODOT_PROTOCOL_VERSION := 2
const LAB_PREVIEW_CONTROLLER := preload("res://lab_preview_controller.gd")
const WORLD_RUNTIME_CONTROLLER := preload("res://runtime/world_controller.gd")
const ACTOR_RUNTIME_CONTROLLER := preload("res://runtime/actor_controller.gd")
const RUNTIME_WEBSOCKET_CLIENT := preload("res://runtime/websocket_client.gd")

@onready var nest: ModularNest = $Nest
@onready var characters: Node3D = $Characters
@onready var lab_preview: Node3D = $LabPreview
@onready var lab_camera: Camera3D = $LabPreview/Camera3D
@onready var camera_stream_bridge: Node = $CameraStreamBridge

var _ws_url := ""
var _lab_mode := false
var _nest_lab_mode := false
var _lab_controller: Node
var _lab_window: JavaScriptObject
var _world_controller: Node
var _actor_controller: Node
var _runtime_client: Node


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
	if _lab_mode:
		_setup_lab_preview()
		return
	if _nest_lab_mode:
		_disable_camera_stream()
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


func _process(_delta: float) -> void:
	if _lab_mode:
		_poll_lab_messages()
		if get_viewport().get_camera_3d() != lab_camera:
			lab_camera.make_current()
		return
	_runtime_client.process_frame()


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
			pass


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
		if (
			command_id.is_empty()
			or String(message.get("correlation_id", "")) != command_id
		):
			return false
	return true


func _on_runtime_event(
	event_name: String,
	payload: Dictionary,
	correlation_id: String,
) -> void:
	_send_runtime_event(event_name, payload, correlation_id)


func _resolve_handshake_nonce() -> String:
	var environment_nonce := OS.get_environment("ELFIENEST_GODOT_NONCE")
	if not environment_nonce.is_empty():
		return environment_nonce
	if not OS.has_feature("web"):
		return ""
	return _query_parameter("nonce")


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


func _setup_lab_preview() -> void:
	nest.visible = false
	nest.process_mode = Node.PROCESS_MODE_DISABLED
	for camera in nest.find_children("*", "Camera3D", true, false):
		(camera as Camera3D).current = false
	lab_preview.visible = true
	lab_camera.make_current()
	_disable_camera_stream()
	_lab_controller = LAB_PREVIEW_CONTROLLER.new()
	add_child(_lab_controller)
	_lab_controller.setup(characters, lab_camera, ACTOR_SCENES)
	_lab_controller.capture_requested.connect(_capture_lab_portrait)
	_disable_nest_cameras.call_deferred()
	_lab_window = JavaScriptBridge.get_interface("window")
	if _lab_window == null:
		return
	JavaScriptBridge.eval(
		"(() => { window.__elfieLabQueue = [];"
		+ " window.elfieLabEnqueue = (data) => {"
		+ " if (typeof data === 'string') window.__elfieLabQueue.push(data); };"
		+ " })()"
	)
	_post_lab_message("ready", {})


func _disable_camera_stream() -> void:
	"""Keep developer Web previews from calling production camera endpoints."""
	camera_stream_bridge.process_mode = Node.PROCESS_MODE_DISABLED


func _disable_nest_cameras() -> void:
	await get_tree().process_frame
	for camera in nest.find_children("*", "Camera3D", true, false):
		(camera as Camera3D).current = false
	lab_camera.make_current()


func _poll_lab_messages() -> void:
	var raw_batch: Variant = JavaScriptBridge.eval(
		"window.__elfieLabQueue && window.__elfieLabQueue.length"
		+ " ? JSON.stringify(window.__elfieLabQueue.splice(0)) : ''"
	)
	if not raw_batch is String or String(raw_batch).is_empty():
		return
	var parsed_batch: Variant = JSON.parse_string(String(raw_batch))
	if not parsed_batch is Array:
		return
	for raw_message: Variant in parsed_batch as Array:
		if raw_message is String:
			_handle_lab_message(String(raw_message))


func _handle_lab_message(raw_message: String) -> void:
	var parsed: Variant = JSON.parse_string(raw_message)
	if not parsed is Dictionary:
		_post_lab_message("protocol_error", {"reason": "invalid_json"})
		return
	var message := parsed as Dictionary
	if String(message.get("channel", "")) != "elfie-lab":
		_post_lab_message("protocol_error", {"reason": "invalid_channel"})
		return
	var normalized := _normalize_lab_message(message)
	_post_lab_message("accepted", {
		"request_id": String(normalized.get("request_id", "")),
		"action": String(normalized.get("action", "")),
	})
	var result: Dictionary = _lab_controller.handle_message(normalized)
	_post_lab_message(String(result.get("event", "unsupported")), result)


func _normalize_lab_message(message: Dictionary) -> Dictionary:
	if message.get("payload") is Dictionary:
		return message
	var payload := {}
	for field in ["elfie_id", "species_id", "spec_revision", "appearance", "delta", "target", "intent"]:
		if message.has(field):
			payload[field] = message[field]
	return message.merged({"payload": payload}, true)


func _capture_lab_portrait(request_id: String) -> void:
	await get_tree().process_frame
	var image := get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		return
	if image.get_width() > 720:
		var target_height := roundi(
			float(image.get_height()) * 720.0 / float(image.get_width())
		)
		image.resize(720, target_height, Image.INTERPOLATE_LANCZOS)
	var data_url := "data:image/png;base64,%s" % Marshalls.raw_to_base64(
		image.save_png_to_buffer()
	)
	_post_lab_message("portrait", {"request_id": request_id, "data_url": data_url})


func _post_lab_message(event_name: String, payload: Dictionary) -> void:
	if _lab_window == null:
		return
	_lab_window.parent.postMessage(
		JSON.stringify({"channel": "elfie-lab", "event": event_name}.merged(payload)),
		String(_lab_window.location.origin),
	)
