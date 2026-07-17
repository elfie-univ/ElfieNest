extends Node3D

const ACTOR_SCENE := preload("res://characters/elfie/elfie_3d.tscn")
const GODOT_WS_URL := "ws://127.0.0.1:8765"
const GODOT_PROTOCOL_VERSION := 1

@onready var nest: ModularNest = $Nest
@onready var characters: Node3D = $Characters

var _socket := WebSocketPeer.new()
var _actors: Dictionary = {}
var _connected := false
var _handshake_complete := false
var _handshake_nonce := ""


func add_character(
	character_scene: PackedScene, spawn_position: Vector3 = Vector3.ZERO
) -> CharacterBody3D:
	var instance := character_scene.instantiate()
	if not instance is CharacterBody3D:
		instance.queue_free()
		push_error("Character scene root must be CharacterBody3D")
		return null

	var character := instance as CharacterBody3D
	characters.add_child(character)
	character.position = spawn_position
	return character


func _ready() -> void:
	var ws_url := OS.get_environment("ELFIENEST_GODOT_WS")
	if ws_url.is_empty():
		ws_url = GODOT_WS_URL
	_handshake_nonce = _resolve_handshake_nonce()
	_socket.connect_to_url(ws_url)


func _process(_delta: float) -> void:
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
			var actor := add_character(ACTOR_SCENE, _spawn_position(index)) as ElfieActor
			if actor == null:
				continue
			actor.configure(identity, actor.position)
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


func _resolve_handshake_nonce() -> String:
	var environment_nonce := OS.get_environment("ELFIENEST_GODOT_NONCE")
	if not environment_nonce.is_empty():
		return environment_nonce
	if not OS.has_feature("web"):
		return ""
	var query: Variant = JavaScriptBridge.eval("window.location.search")
	if not query is String:
		return ""
	for part in String(query).trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2 and pair[0] == "nonce":
			return String(pair[1]).uri_decode()
	return ""
