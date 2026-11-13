extends SceneTree

## Cleanup-only host for the Python Gateway acceptance helper, without reconnect.
## A zero exit code means the connected authority closed, not E2E acceptance.
const WATCHDOG_MSEC := 110_000

var _main: Node
var _started_at_msec := 0


func _init() -> void:
	_started_at_msec = Time.get_ticks_msec()
	call_deferred("_run")


func _run() -> void:
	# main owns authority mode, credentials, transport and all Runtime behavior.
	var scene := load("res://main.tscn") as PackedScene
	if scene == null:
		await _finish(1, "Gateway estate main scene could not be loaded")
		return
	_main = scene.instantiate()
	root.add_child(_main)
	var connected_socket: WebSocketPeer = null
	while Time.get_ticks_msec() - _started_at_msec < WATCHDOG_MSEC:
		await process_frame
		if not is_instance_valid(_main):
			await _finish(1, "Gateway estate main scene was freed unexpectedly")
			return
		var client := _main.get("_runtime_client") as Node
		if client == null:
			await _finish(1, "Gateway estate main has no authority Runtime client")
			return
		if connected_socket == null:
			var socket := client.get("_socket") as WebSocketPeer
			if (
				socket != null
				and socket.get_ready_state() == WebSocketPeer.STATE_OPEN
				and bool(client.get("_handshake_complete"))
			):
				# Retain this peer: main may replace _socket on its first closed frame.
				connected_socket = socket
		if (
			connected_socket != null
			and connected_socket.get_ready_state() == WebSocketPeer.STATE_CLOSED
		):
			await _finish(0)
			return
	await _finish(1, "Gateway estate 110s watchdog expired waiting for handshake/close")


func _finish(exit_code: int, reason: String = "") -> void:
	if not reason.is_empty():
		push_error(reason)
	if is_instance_valid(_main):
		_main.queue_free()
		_main = null
		await process_frame
	quit(exit_code)
