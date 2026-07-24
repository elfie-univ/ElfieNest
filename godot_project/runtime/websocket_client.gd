class_name NestRuntimeWebSocketClient
extends Node

signal command_message(message: Dictionary)

const GODOT_PROTOCOL_VERSION := 2
const RECONNECT_DELAY_SEC := 1.0
const MAX_RECONNECT_DELAY_SEC := 16.0

var runtime_id := ""
var runtime_generation := 0

var _socket := WebSocketPeer.new()
var _connected := false
var _handshake_complete := false
var _handshake_nonce := ""
var _message_sequence := 0
var _ws_url := ""
var _next_reconnect_at := 0.0
var _reconnect_attempt := 0


func setup(ws_url: String, handshake_nonce: String) -> void:
	runtime_id = "godot-%d" % Time.get_unix_time_from_system()
	_ws_url = ws_url
	_handshake_nonce = handshake_nonce
	_connect_websocket()


func process_frame() -> void:
	_socket.poll()
	var state := _socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN and not _connected:
		_connected = true
		_reconnect_attempt = 0
		_handshake_complete = false
		_send_event(
			"hello",
			{
				"protocol": GODOT_PROTOCOL_VERSION,
				"nonce": _handshake_nonce,
				"runtime_id": runtime_id,
			},
		)
	if state != WebSocketPeer.STATE_OPEN:
		_connected = false
		_handshake_complete = false
		if state == WebSocketPeer.STATE_CLOSED:
			_reconnect_when_due()
		return
	while _socket.get_available_packet_count() > 0:
		var packet := _socket.get_packet().get_string_from_utf8()
		_handle_message(packet)


func send_runtime_event(
	event_name: String,
	payload: Dictionary,
	world_revision: int,
	correlation_id: String = "",
) -> void:
	_message_sequence += 1
	var frame := {
		"kind": "event",
		"protocol": GODOT_PROTOCOL_VERSION,
		"name": event_name,
		"message_id": "%s-%06d" % [runtime_id, _message_sequence],
		"runtime_id": runtime_id,
		"generation": runtime_generation,
		"world_revision": world_revision,
		"occurred_at": "%sZ" % Time.get_datetime_string_from_system(true),
		"payload": payload,
	}
	if not correlation_id.is_empty():
		frame["correlation_id"] = correlation_id
	_socket.send_text(JSON.stringify(frame))


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
		var hello_payload: Variant = message.get("payload", {})
		if hello_payload is Dictionary:
			runtime_generation = int(
				(hello_payload as Dictionary).get("generation", 0)
			)
		return
	if _handshake_complete and String(message.get("kind", "")) == "command":
		command_message.emit(message)


func _reconnect_when_due() -> void:
	var now := Time.get_ticks_msec() / 1000.0
	if now < _next_reconnect_at:
		return
	var retry_delay := minf(
		RECONNECT_DELAY_SEC * pow(2.0, _reconnect_attempt),
		MAX_RECONNECT_DELAY_SEC,
	)
	_reconnect_attempt = mini(_reconnect_attempt + 1, 5)
	_next_reconnect_at = now + retry_delay
	_connect_websocket()


func _connect_websocket() -> void:
	_socket = WebSocketPeer.new()
	_connected = false
	_handshake_complete = false
	var connect_error := _socket.connect_to_url(_ws_url)
	if connect_error != OK:
		push_error(
			"Runtime WebSocket connection could not be started: %d" % connect_error
		)
