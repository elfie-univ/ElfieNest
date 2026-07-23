extends Node

signal capture_requested(request_id: String)

const MAX_REQUEST_HISTORY := 256
const MAX_REQUEST_ID_LENGTH := 128
const MAX_ORBIT_DELTA := 4.0
const MAX_PAN_DELTA := 2.0
const MAX_ZOOM_DELTA := 1.0
const MIN_CAMERA_SIZE := 1.2
const MAX_CAMERA_SIZE := 4.0
const BUST_HEIGHT_RATIO := 0.62
const BUST_FRAME_MARGIN := 1.12
const SUPPORTED_ACTIONS := {
	"configure": true,
	"orbit": true,
	"pan": true,
	"zoom": true,
	"focus": true,
	"reset": true,
	"capture": true,
	"preview_intent": true,
}
const FOCUS_TARGETS := {"actor": true, "body": true, "head": true}

var _characters: Node3D
var _camera: Camera3D
var _actor_scenes: Dictionary
var _actor_factory: Callable
var _actor: Node3D
var _elfie_id := ""
var _species_id := ""
var _spec_revision := -1
var _focus_point := Vector3(0.0, 0.9, 0.0)
var _default_focus_point := Vector3(0.0, 0.9, 0.0)
var _yaw := 0.0
var _pitch := 0.0
var _distance := 3.4
var _default_camera_size := 2.35
var _request_fingerprints: Dictionary = {}
var _request_results: Dictionary = {}
var _request_order: Array[String] = []


func setup(
	characters: Node3D,
	camera: Camera3D,
	actor_scenes: Dictionary,
	actor_factory: Callable = Callable(),
) -> void:
	_characters = characters
	_camera = camera
	_actor_scenes = actor_scenes
	_actor_factory = actor_factory
	_default_camera_size = camera.size


func handle_message(message: Dictionary) -> Dictionary:
	if _characters == null or _camera == null:
		return _unsupported("", "", "controller_not_ready")
	if String(message.get("channel", "")) != "elfie-lab":
		return _unsupported("", String(message.get("action", "")), "invalid_channel")
	var request_id := String(message.get("request_id", ""))
	var action := String(message.get("action", ""))
	if request_id.is_empty() or request_id.length() > MAX_REQUEST_ID_LENGTH:
		return _unsupported(request_id, action, "invalid_request_id")
	if action.is_empty() or not SUPPORTED_ACTIONS.has(action):
		return _unsupported(request_id, action, "unsupported_action")
	var payload: Variant = message.get("payload", {})
	if not payload is Dictionary:
		return _remember(message, _unsupported(request_id, action, "invalid_payload"))
	if _request_fingerprints.has(request_id):
		var fingerprint := str(message)
		if _request_fingerprints[request_id] == fingerprint:
			return (_request_results[request_id] as Dictionary).duplicate(true)
		return _unsupported(request_id, action, "request_id_conflict")

	var result := _dispatch(action, payload as Dictionary, request_id)
	return _remember(message, result)


func actor_count() -> int:
	return _characters.get_child_count() if _characters != null else 0


func _dispatch(action: String, payload: Dictionary, request_id: String) -> Dictionary:
	match action:
		"configure":
			return _configure(payload, request_id)
		"orbit":
			return _orbit(payload, request_id)
		"pan":
			return _pan(payload, request_id)
		"zoom":
			return _zoom(payload, request_id)
		"focus":
			return _focus(payload, request_id)
		"reset":
			return _reset(request_id)
		"capture":
			return _capture(request_id)
		"preview_intent":
			return _preview_intent(payload, request_id)
	return _unsupported(request_id, action, "unsupported_action")


func _configure(payload: Dictionary, request_id: String) -> Dictionary:
	var elfie_id := String(payload.get("elfie_id", ""))
	var species_id := String(payload.get("species_id", ""))
	var revision: Variant = payload.get("spec_revision")
	var appearance: Variant = payload.get("appearance", {})
	if elfie_id.is_empty() or elfie_id.length() > 128:
		return _unsupported(request_id, "configure", "invalid_elfie_id")
	if not _actor_scenes.has(species_id):
		return _unsupported(request_id, "configure", "unsupported_species")
	if (
		not (revision is int or revision is float)
		or not is_finite(float(revision))
		or float(revision) < 0.0
		or float(revision) != floorf(float(revision))
	):
		return _unsupported(request_id, "configure", "invalid_spec_revision")
	var revision_value := int(revision)
	if not appearance is Dictionary:
		return _unsupported(request_id, "configure", "invalid_appearance")
	if (
		_actor != null
		and is_instance_valid(_actor)
		and _elfie_id == elfie_id
		and _species_id == species_id
		and _spec_revision == revision_value
	):
		return _completed(request_id, "configure", {"reused_actor": true})

	var scene := _actor_scenes[species_id] as PackedScene
	var candidate: Variant = (
		_actor_factory.call(species_id, scene)
		if _actor_factory.is_valid()
		else scene.instantiate()
	)
	if not candidate is Node3D or not (candidate as Node3D).has_method("configure"):
		if candidate is Node:
			(candidate as Node).free()
		return _unsupported(request_id, "configure", "actor_creation_failed")
	if _actor != null and is_instance_valid(_actor):
		_actor.free()
	_actor = candidate as Node3D
	if _actor.has_method("prepare_preview"):
		_actor.call("prepare_preview")
	_characters.add_child(_actor)
	_actor.call("configure", elfie_id, Vector3.ZERO, appearance as Dictionary)
	if _actor is CharacterBody3D:
		(_actor as CharacterBody3D).velocity = Vector3.ZERO
	_actor.set_physics_process(false)
	_actor.rotation = Vector3.ZERO
	_elfie_id = elfie_id
	_species_id = species_id
	_spec_revision = revision_value
	_frame_actor()
	return _completed(request_id, "configure", {"reused_actor": false})


func _orbit(payload: Dictionary, request_id: String) -> Dictionary:
	var delta: Variant = _vector2(payload.get("delta"), MAX_ORBIT_DELTA)
	if delta == null:
		return _unsupported(request_id, "orbit", "invalid_delta")
	_yaw += (delta as Vector2).x
	_pitch = clampf(_pitch + (delta as Vector2).y, -1.2, 1.2)
	_apply_camera()
	return _completed(request_id, "orbit")


func _pan(payload: Dictionary, request_id: String) -> Dictionary:
	var delta: Variant = _vector2(payload.get("delta"), MAX_PAN_DELTA)
	if delta == null:
		return _unsupported(request_id, "pan", "invalid_delta")
	var right := Vector3(cos(_yaw), 0.0, -sin(_yaw))
	_focus_point += right * (delta as Vector2).x + Vector3.UP * (delta as Vector2).y
	_apply_camera()
	return _completed(request_id, "pan")


func _zoom(payload: Dictionary, request_id: String) -> Dictionary:
	var delta: Variant = payload.get("delta")
	if not _valid_number(delta, MAX_ZOOM_DELTA):
		return _unsupported(request_id, "zoom", "invalid_delta")
	_camera.size = clampf(_camera.size + float(delta), MIN_CAMERA_SIZE, MAX_CAMERA_SIZE)
	return _completed(request_id, "zoom")


func _focus(payload: Dictionary, request_id: String) -> Dictionary:
	if not _has_actor():
		return _unsupported(request_id, "focus", "actor_not_configured")
	var target := String(payload.get("target", ""))
	if not FOCUS_TARGETS.has(target):
		return _unsupported(request_id, "focus", "unsupported_focus")
	if target == "head":
		var bounds := _actor.call("visual_bounds") as AABB
		var bust_height := bounds.size.y * BUST_HEIGHT_RATIO
		_focus_point = Vector3(
			bounds.get_center().x,
			bounds.end.y - bust_height * 0.5,
			bounds.get_center().z,
		)
		var viewport_size := _camera.get_viewport().get_visible_rect().size
		var aspect := viewport_size.x / maxf(viewport_size.y, 1.0)
		_camera.size = clampf(
			maxf(bust_height, bounds.size.x / maxf(aspect, 0.1)) * BUST_FRAME_MARGIN,
			MIN_CAMERA_SIZE,
			MAX_CAMERA_SIZE,
		)
	else:
		_focus_point = (
			_actor.call("preview_focus_point", target)
			if _actor.has_method("preview_focus_point")
			else _bounds_focus(target)
		)
	_apply_camera()
	return _completed(request_id, "focus", {"target": target})


func _reset(request_id: String) -> Dictionary:
	if not _has_actor():
		return _unsupported(request_id, "reset", "actor_not_configured")
	_actor.rotation = Vector3.ZERO
	_focus_point = _default_focus_point
	_yaw = 0.0
	_pitch = 0.0
	_camera.size = _default_camera_size
	_apply_camera()
	return _completed(request_id, "reset")


func _capture(request_id: String) -> Dictionary:
	if not _has_actor():
		return _unsupported(request_id, "capture", "actor_not_configured")
	capture_requested.emit(request_id)
	return _completed(request_id, "capture")


func _preview_intent(payload: Dictionary, request_id: String) -> Dictionary:
	if not _has_actor():
		return _unsupported(request_id, "preview_intent", "actor_not_configured")
	var intent_value: Variant = payload.get("intent")
	if not intent_value is Dictionary:
		return _unsupported(request_id, "preview_intent", "invalid_intent")
	var intent := (intent_value as Dictionary).duplicate(true)
	var intent_type := String(intent.get("type", ""))
	var intent_id := String(intent.get("intent_id", ""))
	if not ["motion", "expression"].has(intent_type) or intent_id.is_empty() or intent_id.length() > 128:
		return _unsupported(request_id, "preview_intent", "invalid_intent")
	if not _actor.has_method("play_preview_intent"):
		return _unsupported(request_id, "preview_intent", "intent_not_supported")
	if not bool(_actor.call("play_preview_intent", intent)):
		return _unsupported(request_id, "preview_intent", "intent_not_supported")
	return _completed(request_id, "preview_intent", {"intent": intent})


func _frame_actor() -> void:
	var bounds := _actor.call("visual_bounds") as AABB
	_focus_point = bounds.get_center()
	_default_focus_point = _focus_point
	_distance = maxf(3.0, bounds.size.z * 2.0)
	var viewport_size := _camera.get_viewport().get_visible_rect().size
	var aspect := viewport_size.x / maxf(viewport_size.y, 1.0)
	_default_camera_size = clampf(
		maxf(bounds.size.y, bounds.size.x / maxf(aspect, 0.1)) * 1.16,
		MIN_CAMERA_SIZE,
		MAX_CAMERA_SIZE,
	)
	_camera.size = _default_camera_size
	_yaw = 0.0
	_pitch = 0.0
	_apply_camera()


func _apply_camera() -> void:
	var horizontal := cos(_pitch) * _distance
	_camera.global_position = _focus_point + Vector3(
		sin(_yaw) * horizontal,
		sin(_pitch) * _distance,
		cos(_yaw) * horizontal,
	)
	_camera.look_at(_focus_point, Vector3.UP)


func _bounds_focus(target: String) -> Vector3:
	var bounds := _actor.call("visual_bounds") as AABB
	if target == "head":
		return Vector3(bounds.get_center().x, bounds.end.y - bounds.size.y * 0.12, bounds.get_center().z)
	return bounds.get_center()


func _vector2(value: Variant, maximum: float) -> Variant:
	if not value is Dictionary:
		return null
	var x: Variant = (value as Dictionary).get("x")
	var y: Variant = (value as Dictionary).get("y")
	if not _valid_number(x, maximum) or not _valid_number(y, maximum):
		return null
	return Vector2(float(x), float(y))


func _valid_number(value: Variant, maximum: float) -> bool:
	return (
		(value is float or value is int)
		and is_finite(float(value))
		and absf(float(value)) <= maximum
	)


func _has_actor() -> bool:
	return _actor != null and is_instance_valid(_actor)


func _remember(message: Dictionary, result: Dictionary) -> Dictionary:
	var request_id := String(message.get("request_id", ""))
	_request_fingerprints[request_id] = str(message)
	_request_results[request_id] = result.duplicate(true)
	_request_order.append(request_id)
	if _request_order.size() > MAX_REQUEST_HISTORY:
		var expired := String(_request_order.pop_front())
		_request_fingerprints.erase(expired)
		_request_results.erase(expired)
	return result


func _completed(request_id: String, action: String, details: Dictionary = {}) -> Dictionary:
	return {
		"channel": "elfie-lab",
		"event": "completed",
		"request_id": request_id,
		"action": action,
	}.merged(details)


func _unsupported(request_id: String, action: String, reason: String) -> Dictionary:
	return {
		"channel": "elfie-lab",
		"event": "unsupported",
		"request_id": request_id,
		"action": action,
		"reason": reason,
	}
