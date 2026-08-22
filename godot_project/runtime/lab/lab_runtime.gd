extends Node

const LAB_PREVIEW_CONTROLLER := preload("res://lab_preview_controller.gd")

var _nest: ModularNest
var _characters: Node3D
var _lab_preview: Node3D
var _lab_camera: Camera3D
var _actor_scenes: Dictionary
var _lab_controller: Node
var _lab_browser_bridge_ready := false


func setup(
	nest: ModularNest,
	characters: Node3D,
	lab_preview: Node3D,
	lab_camera: Camera3D,
	actor_scenes: Dictionary,
) -> void:
	"""Bind the scene nodes owned by the browser-only lab modes."""
	_nest = nest
	_characters = characters
	_lab_preview = lab_preview
	_lab_camera = lab_camera
	_actor_scenes = actor_scenes


func setup_elfie_lab() -> void:
	"""Start the isolated Elfie Lab preview without authority transport."""
	_nest.visible = false
	_nest.process_mode = Node.PROCESS_MODE_DISABLED
	for camera in _nest.find_children("*", "Camera3D", true, false):
		(camera as Camera3D).current = false
	_lab_preview.visible = true
	_lab_camera.make_current()
	_lab_controller = LAB_PREVIEW_CONTROLLER.new()
	add_child(_lab_controller)
	_lab_controller.setup(_characters, _lab_camera, _actor_scenes)
	_lab_controller.capture_requested.connect(_capture_lab_portrait)
	_disable_nest_cameras.call_deferred()
	_initialize_lab_browser_bridge()


func setup_nest_lab() -> void:
	"""Start the same-origin named-camera bridge used by Nest Lab."""
	JavaScriptBridge.eval(
		"(() => { window.__elfieNestLabCameraQueue = [];"
		+ " window.addEventListener('message', (event) => {"
		+ " if (event.origin !== window.location.origin) return;"
		+ " const data = event.data;"
		+ " if (data && data.channel === 'elfienest-nest-lab'"
		+ " && data.type === 'camera' && typeof data.intent === 'string')"
		+ " window.__elfieNestLabCameraQueue.push(data.intent);"
		+ " }); })()"
	)


func process_elfie_lab_frame() -> void:
	_poll_lab_messages()
	_initialize_lab_browser_bridge()
	if get_viewport().get_camera_3d() != _lab_camera:
		_lab_camera.make_current()


func process_nest_lab_frame() -> void:
	var raw_batch: Variant = JavaScriptBridge.eval(
		"window.__elfieNestLabCameraQueue && window.__elfieNestLabCameraQueue.length"
		+ " ? JSON.stringify(window.__elfieNestLabCameraQueue.splice(0)) : ''"
	)
	if not raw_batch is String or String(raw_batch).is_empty():
		return
	var parsed_batch: Variant = JSON.parse_string(String(raw_batch))
	if not parsed_batch is Array:
		return
	for raw_intent: Variant in parsed_batch as Array:
		if raw_intent is String:
			_select_nest_lab_camera_preset(String(raw_intent))


func _initialize_lab_browser_bridge() -> void:
	if _lab_browser_bridge_ready:
		return
	JavaScriptBridge.eval(
		"(() => { window.__elfieLabQueue = window.__elfieLabQueue || [];"
		+ " window.__elfieLabReady = true;"
		+ " window.elfieLabEnqueue = (data) => {"
		+ " if (typeof data === 'string') window.__elfieLabQueue.push(data); };"
		+ " window.addEventListener('message', (event) => {"
		+ " if (event.origin !== window.location.origin || event.source !== window.parent) return;"
		+ " const data = event.data;"
		+ " if (typeof data === 'string') window.__elfieLabQueue.push(data);"
		+ " else if (data && data.channel === 'elfie-lab')"
		+ " window.__elfieLabQueue.push(JSON.stringify(data));"
		+ " });"
		+ " })()"
	)
	_lab_browser_bridge_ready = true
	_post_lab_message("ready", {})


func _select_nest_lab_camera_preset(intent: String) -> void:
	match intent:
		"overview":
			_nest.select_observation_view(0)
		"activity":
			_nest.select_observation_view_named("活动")
		"dorm":
			_nest.select_observation_view_named("宿舍")
		"portal":
			_nest.select_observation_view_named("传送室")
		"restore":
			_nest.reset_observation_camera()
		_:
			return


func _disable_nest_cameras() -> void:
	await get_tree().process_frame
	for camera in _nest.find_children("*", "Camera3D", true, false):
		(camera as Camera3D).current = false
	_lab_camera.make_current()


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
	# WebGL may compile a newly assigned ShaderMaterial asynchronously. Let the
	# material settle before reading the viewport, otherwise the first portrait
	# can capture the renderer's black fallback for every candidate.
	for _frame_index in range(3):
		await get_tree().process_frame
	# Camera focus/orbit changes are applied during the frame; wait for the
	# completed render pass so the captured PNG matches the visible 3D stage.
	await RenderingServer.frame_post_draw
	var canvas_data_url := await _capture_browser_canvas()
	if not canvas_data_url.is_empty():
		_post_lab_message("portrait", {"request_id": request_id, "data_url": canvas_data_url})
		return
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


func _capture_browser_canvas() -> String:
	if not OS.has_feature("web"):
		return ""
	# Godot's render loop and the browser's paint loop are separate. Reading the
	# WebGL canvas synchronously here can therefore return the previous camera
	# frame (for example, the full-body frame after selecting "portrait"). Ask
	# the browser to read the canvas after two animation frames, then retrieve
	# that completed PNG from the next few Godot frames.
	JavaScriptBridge.eval(
		"(() => {"
		+ " window.__elfieLabCaptureData = '';"
		+ " const capture = () => {"
		+ " const canvas = document.querySelector('canvas');"
		+ " if (!canvas || typeof canvas.toDataURL !== 'function') return;"
		+ " try {"
		+ " const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');"
		+ " if (gl && typeof gl.finish === 'function') gl.finish();"
		+ " window.__elfieLabCaptureData = canvas.toDataURL('image/png');"
		+ " }"
		+ " catch (_) { window.__elfieLabCaptureData = ''; }"
		+ " };"
		+ " if (typeof window.requestAnimationFrame === 'function')"
		+ " requestAnimationFrame(() => requestAnimationFrame(capture));"
		+ " else setTimeout(capture, 0);"
		+ "})()"
	)
	for _frame_index in range(6):
		await get_tree().process_frame
	var raw_data_url: Variant = JavaScriptBridge.eval(
		"window.__elfieLabCaptureData || ''"
	)
	if not raw_data_url is String:
		return ""
	var data_url := String(raw_data_url)
	return data_url if data_url.begins_with("data:image/png;base64,") else ""


func _post_lab_message(event_name: String, payload: Dictionary) -> void:
	var message := {"channel": "elfie-lab", "event": event_name}.merged(payload)
	var serialized := JSON.stringify(message)
	# Use eval for the outbound handshake too. It does not depend on a window
	# proxy being exposed by the Web export at the exact startup frame.
	JavaScriptBridge.eval(
		"window.parent.postMessage(%s, window.location.origin)"
		% JSON.stringify(serialized)
	)
