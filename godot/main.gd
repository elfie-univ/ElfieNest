extends Node3D

const ACTOR_SCENES := {
	"dog": preload("res://characters/dog/dog.tscn"),
	"fox": preload("res://characters/fox/fox.tscn"),
}
const GODOT_WS_URL := "ws://127.0.0.1:8765"
const GODOT_PROTOCOL_VERSION := 1
const RECONNECT_DELAY_SEC := 1.0
const LAB_PREVIEW_CONTROLLER := preload("res://lab_preview_controller.gd")

@onready var nest: ModularNest = $Nest
@onready var characters: Node3D = $Characters
@onready var lab_preview: Node3D = $LabPreview
@onready var lab_camera: Camera3D = $LabPreview/Camera3D
@onready var camera_stream_bridge: Node = $CameraStreamBridge

var _socket := WebSocketPeer.new()
var _actors: Dictionary = {}
var _connected := false
var _handshake_complete := false
var _handshake_nonce := ""
var _ws_url := ""
var _next_reconnect_at := 0.0
var _lab_mode := false
var _lab_controller: Node
var _lab_window: JavaScriptObject


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
	if _lab_mode:
		_setup_lab_preview()
		return
	_ws_url = OS.get_environment("ELFIENEST_GODOT_WS")
	if _ws_url.is_empty():
		_ws_url = GODOT_WS_URL
	_handshake_nonce = _resolve_handshake_nonce()
	_connect_websocket()


func _process(_delta: float) -> void:
	if _lab_mode:
		_poll_lab_messages()
		if get_viewport().get_camera_3d() != lab_camera:
			lab_camera.make_current()
		return
	_socket.poll()
	var state := _socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN and not _connected:
		_connected = true
		_handshake_complete = false
		_send_event(
			"hello",
			{"protocol": GODOT_PROTOCOL_VERSION, "nonce": _handshake_nonce}
		)
	if state != WebSocketPeer.STATE_OPEN:
		_connected = false
		_handshake_complete = false
		if state == WebSocketPeer.STATE_CLOSED:
			var now := Time.get_ticks_msec() / 1000.0
			if now >= _next_reconnect_at:
				_next_reconnect_at = now + RECONNECT_DELAY_SEC
				_connect_websocket()
		return
	while _socket.get_available_packet_count() > 0:
		var packet := _socket.get_packet().get_string_from_utf8()
		_handle_message(packet)


func _send_event(event_name: String, payload: Dictionary) -> void:
	_socket.send_text(JSON.stringify({"event": event_name, "payload": payload}))


func _handle_message(raw_message: String) -> void:
	var parsed: Variant = JSON.parse_string(raw_message)
	if not parsed is Dictionary:
		return
	var message := parsed as Dictionary
	var event_name := String(message.get("event", ""))
	if event_name == "hello_ok":
		_handshake_complete = true
		_send_event("runtime_ready", {"protocol": GODOT_PROTOCOL_VERSION, "bed_count": nest.bed_count})
		return
	if not _handshake_complete:
		return
	var action := String(message.get("action", ""))
	var payload: Variant = message.get("payload", {})
	if not payload is Dictionary:
		return
	match action:
		"sync_elfies":
			_sync_elfies((payload as Dictionary).get("elfies", []))
		"go_to":
			_apply_go_to(payload as Dictionary)
		"speak_event", "emotion_expression":
			_apply_expression(payload as Dictionary)
		_:
			pass


func _sync_elfies(raw_elfies: Variant) -> void:
	if not raw_elfies is Array:
		return
	var expected := {}
	var index := 0
	for raw_elfie in raw_elfies as Array:
		if not raw_elfie is Dictionary:
			continue
		var identity := String((raw_elfie as Dictionary).get("elfie_id", ""))
		if identity.is_empty():
			continue
		expected[identity] = true
		if not _actors.has(identity):
			var elfie_data := raw_elfie as Dictionary
			var actor_scene := _actor_scene_for(elfie_data, identity)
			var actor := add_character(actor_scene, _spawn_position(index)) as ElfieActor
			if actor == null:
				continue
			var appearance := elfie_data.get("appearance", elfie_data) as Dictionary
			actor.configure(identity, actor.position, appearance)
			_actors[identity] = actor
		index += 1
	var stale_ids: Array[String] = []
	for identity in _actors.keys():
		if not expected.has(identity):
			stale_ids.append(String(identity))
	for identity in stale_ids:
		_actors[identity].queue_free()
		_actors.erase(identity)


func _apply_go_to(payload: Dictionary) -> void:
	var identity := String(payload.get("elfie_id", ""))
	var actor := _actors.get(identity) as ElfieActor
	if actor == null:
		return
	actor.set_target_name(String(payload.get("target", "")))


func _apply_expression(_payload: Dictionary) -> void:
	# 表情和语音先保留协议入口，动画驱动将在角色控制器阶段接入。
	pass


func _spawn_position(index: int) -> Vector3:
	var column := index % 4
	var row := index / 4
	return Vector3(-1.2 + float(column) * 0.8, 0.0, -2.5 - float(row) * 1.2)


func _actor_scene_for(elfie_data: Dictionary, identity: String) -> PackedScene:
	var species := String(elfie_data.get("species", ""))
	if ACTOR_SCENES.has(species):
		return ACTOR_SCENES[species] as PackedScene
	push_warning("精灵 %s 缺少合法 species，使用 fox 兼容母版" % identity)
	return ACTOR_SCENES["fox"] as PackedScene


func _resolve_handshake_nonce() -> String:
	var environment_nonce := OS.get_environment("ELFIENEST_GODOT_NONCE")
	if not environment_nonce.is_empty():
		return environment_nonce
	if not OS.has_feature("web"):
		return ""
	return _query_parameter("nonce")


func _query_parameter(name: String) -> String:
	var query: Variant = JavaScriptBridge.eval("window.location.search")
	if not query is String:
		return ""
	for part in String(query).trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2 and pair[0] == name:
			return String(pair[1]).uri_decode()
	return ""


func _connect_websocket() -> void:
	_socket = WebSocketPeer.new()
	_connected = false
	_handshake_complete = false
	_socket.connect_to_url(_ws_url)


func _setup_lab_preview() -> void:
	nest.visible = false
	nest.process_mode = Node.PROCESS_MODE_DISABLED
	for camera in nest.find_children("*", "Camera3D", true, false):
		(camera as Camera3D).current = false
	lab_preview.visible = true
	lab_camera.make_current()
	camera_stream_bridge.process_mode = Node.PROCESS_MODE_DISABLED
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
