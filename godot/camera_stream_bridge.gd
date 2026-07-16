class_name CameraStreamBridge
extends Node

const FRAME_WIDTH: int = 960
const FRAME_INTERVAL_SECONDS: float = 0.16
const CONTROL_INTERVAL_SECONDS: float = 0.2
const STATUS_INTERVAL_SECONDS: float = 1.0

@export var api_base_url: String = "http://127.0.0.1:8000/api/godot-camera"
@export var nest_path: NodePath = NodePath("../Nest")

var _nest: ModularNest
var _frame_request: HTTPRequest
var _control_request: HTTPRequest
var _status_request: HTTPRequest
var _layout_update_in_progress: bool = false
var _frame_in_flight: bool = false
var _control_in_flight: bool = false
var _status_in_flight: bool = false


func _ready() -> void:
	var api_override := OS.get_environment("ELFIENEST_CAMERA_API")
	if not api_override.is_empty():
		api_base_url = api_override.trim_suffix("/")
	elif OS.has_feature("web"):
		var location := JavaScriptBridge.get_interface("location")
		if location != null:
			api_base_url = "%s/api/godot-camera" % String(location.origin)
	_nest = get_node_or_null(nest_path) as ModularNest
	if _nest == null:
		push_warning("Camera stream bridge could not find the nest")
		return

	_frame_request = _make_request("FrameRequest")
	_control_request = _make_request("ControlRequest")
	_status_request = _make_request("StatusRequest")
	_frame_request.request_completed.connect(_on_frame_completed)
	_control_request.request_completed.connect(_on_control_completed)
	_status_request.request_completed.connect(_on_status_completed)

	var frame_timer := _make_timer("FrameTimer", FRAME_INTERVAL_SECONDS)
	var control_timer := _make_timer("ControlTimer", CONTROL_INTERVAL_SECONDS)
	var status_timer := _make_timer("StatusTimer", STATUS_INTERVAL_SECONDS)
	frame_timer.timeout.connect(_capture_frame)
	control_timer.timeout.connect(_poll_control)
	status_timer.timeout.connect(_publish_status)

	for _frame in range(4):
		await get_tree().process_frame
	_notify_web_runtime_ready()
	_publish_status()
	_poll_control()
	_capture_frame()


func _notify_web_runtime_ready() -> void:
	if not OS.has_feature("web"):
		return
	var window := JavaScriptBridge.get_interface("window")
	if window == null:
		return
	window.parent.postMessage("elfienest:godot-web-ready", window.location.origin)


func _make_request(node_name: String) -> HTTPRequest:
	var request := HTTPRequest.new()
	request.name = node_name
	request.timeout = 1.5
	add_child(request)
	return request


func _make_timer(node_name: String, wait_time: float) -> Timer:
	var timer := Timer.new()
	timer.name = node_name
	timer.wait_time = wait_time
	timer.autostart = true
	timer.one_shot = false
	add_child(timer)
	return timer


func _request_available(request: HTTPRequest) -> bool:
	return request.get_http_client_status() == HTTPClient.STATUS_DISCONNECTED


func _capture_frame() -> void:
	if (
		_frame_in_flight
		or not _request_available(_frame_request)
		or _nest.observation_view_count() == 0
	):
		return
	var image := get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		return
	if image.get_width() > FRAME_WIDTH:
		var target_height := roundi(
			float(image.get_height()) * float(FRAME_WIDTH) / float(image.get_width())
		)
		image.resize(FRAME_WIDTH, target_height, Image.INTERPOLATE_BILINEAR)
	var frame := image.save_jpg_to_buffer(0.72)
	var frame_url := "%s/frame?view_index=%d" % [
		api_base_url,
		_nest.observation_active_view_index(),
	]
	var error := _frame_request.request_raw(
		frame_url,
		PackedStringArray(["Content-Type: image/jpeg"]),
		HTTPClient.METHOD_POST,
		frame
	)
	_frame_in_flight = error == OK


func _publish_status() -> void:
	if (
		_status_in_flight
		or not _request_available(_status_request)
		or _nest.observation_view_count() == 0
	):
		return
	var labels: Array[String] = []
	for label in _nest.observation_view_labels():
		labels.append(String(label))
	var body := JSON.stringify({
		"labels": labels,
		"active_index": _nest.observation_active_view_index(),
		"bed_count": _nest.bed_count,
	})
	var error := _status_request.request(
		"%s/status" % api_base_url,
		PackedStringArray(["Content-Type: application/json"]),
		HTTPClient.METHOD_POST,
		body
	)
	_status_in_flight = error == OK


func _poll_control() -> void:
	if _control_in_flight or not _request_available(_control_request):
		return
	var error := _control_request.request("%s/control" % api_base_url)
	_control_in_flight = error == OK


func _on_frame_completed(
	_result: int,
	_response_code: int,
	_headers: PackedStringArray,
	_body: PackedByteArray
) -> void:
	_frame_in_flight = false


func _on_status_completed(
	_result: int,
	_response_code: int,
	_headers: PackedStringArray,
	_body: PackedByteArray
) -> void:
	_status_in_flight = false


func _on_control_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray
) -> void:
	_control_in_flight = false
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		return
	var payload: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not payload is Dictionary:
		return
	if _layout_update_in_progress:
		return
	_apply_control(payload as Dictionary)


func _apply_control(payload: Dictionary) -> void:
	_layout_update_in_progress = true
	var requested_bed_count := clampi(
		int(payload.get("bed_count", _nest.bed_count)),
		1,
		32
	)
	if requested_bed_count != _nest.bed_count:
		_nest.bed_count = requested_bed_count
		for _frame in range(4):
			await get_tree().process_frame
	var requested_index := int(payload.get("view_index", 0))
	if requested_index != _nest.observation_active_view_index():
		_nest.select_observation_view(requested_index)
	_publish_status()
	_layout_update_in_progress = false
