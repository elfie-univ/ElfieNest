class_name NestRuntimeWebSocketClient
extends Node

signal command_message(message: Dictionary)

const GODOT_PROTOCOL_VERSION := 3
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
var _incident_reconnect_attempts := 0
var _total_reconnect_attempts := 0
var _last_socket_state := WebSocketPeer.STATE_CLOSED


func setup(ws_url: String, handshake_nonce: String) -> void:
	runtime_id = "godot-%d" % Time.get_unix_time_from_system()
	_ws_url = ws_url
	_handshake_nonce = handshake_nonce
	_connect_websocket()


func process_frame() -> void:
	_socket.poll()
	var state := _socket.get_ready_state()
	if state != _last_socket_state:
		if state == WebSocketPeer.STATE_OPEN:
			_log_runtime_event("runtime_websocket_opened", {}, "info")
		elif state == WebSocketPeer.STATE_CLOSED:
			_log_runtime_event(
				"runtime_websocket_closed",
				{
					"close_code": _socket.get_close_code(),
					"close_reason": _socket.get_close_reason(),
				},
				"warning",
			)
		_last_socket_state = state
	if state == WebSocketPeer.STATE_OPEN and not _connected:
		_connected = true
		_reconnect_attempt = 0
		_incident_reconnect_attempts = 0
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
	lane: String,
	target_actor_id: String = "",
	cause_id: String = "",
) -> void:
	_message_sequence += 1
	var frame := {
		"kind": "event",
		"protocol": GODOT_PROTOCOL_VERSION,
		"lane": lane,
		"name": event_name,
		"message_id": "%s-%06d" % [runtime_id, _message_sequence],
		"runtime_id": runtime_id,
		"generation": runtime_generation,
		"world_revision": world_revision,
		"occurred_at": "%sZ" % Time.get_datetime_string_from_system(true),
		"payload": payload,
	}
	if not target_actor_id.is_empty():
		frame["target_actor_id"] = target_actor_id
	if not cause_id.is_empty():
		frame["cause_id"] = cause_id
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
		var hello_payload: Variant = message.get("payload", {})
		if not hello_payload is Dictionary:
			return
		var payload := hello_payload as Dictionary
		if int(payload.get("protocol", 0)) != GODOT_PROTOCOL_VERSION:
			return
		_handshake_complete = true
		runtime_generation = int(payload.get("generation", 0))
		_log_runtime_event(
			"runtime_websocket_handshake_complete",
			{"generation": runtime_generation},
			"info",
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
	_incident_reconnect_attempts += 1
	_total_reconnect_attempts += 1
	_next_reconnect_at = now + retry_delay
	if (
		_incident_reconnect_attempts <= 3
		or _incident_reconnect_attempts % 60 == 0
	):
		_log_runtime_event(
			"runtime_websocket_reconnect",
			{
				"attempt": _incident_reconnect_attempts,
				"total_attempts": _total_reconnect_attempts,
				"delay_seconds": retry_delay,
			},
			"warning",
		)
	_connect_websocket()


func _connect_websocket() -> void:
	_socket = WebSocketPeer.new()
	_connected = false
	_handshake_complete = false
	var connect_error := _socket.connect_to_url(_ws_url)
	_last_socket_state = _socket.get_ready_state()
	if connect_error != OK:
		_log_runtime_event(
			"runtime_websocket_connect_failed",
			{"error_code": connect_error},
			"error",
		)


func _log_runtime_event(
	event_name: String,
	fields: Dictionary = {},
	level: String = "info",
) -> void:
	var payload := {
		"timestamp": "%sZ" % Time.get_datetime_string_from_system(true),
		"event": event_name,
		"level": level,
		"role": "godot-runtime",
		"runtime_id": runtime_id,
		"generation": runtime_generation,
	}
	for key: Variant in fields:
		payload[key] = fields[key]
	print(JSON.stringify(payload))
