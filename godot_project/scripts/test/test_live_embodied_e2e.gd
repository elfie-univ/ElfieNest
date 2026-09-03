extends SceneTree

const PROJECT_READINESS := preload("res://scripts/test/project_readiness.gd")
const MAIN_SCENE_PATH := "res://main.tscn"
const CAMERA_VIEW_ENV := "ELFIENEST_E2E_CAMERA_VIEW"

var _main: Node
var _actor: Node3D
var _initial_position := Vector3.ZERO
var _initial_captured := false
var _final_captured := false
var _started_at_msec := 0
var _initial_path := ""
var _final_path := ""
var _report_path := ""
var _actor_id := ""
var _camera_view := ""


func _init() -> void:
	_initial_path = OS.get_environment("ELFIENEST_E2E_INITIAL_SCREENSHOT")
	_final_path = OS.get_environment("ELFIENEST_E2E_FINAL_SCREENSHOT")
	_report_path = OS.get_environment("ELFIENEST_E2E_GODOT_REPORT")
	_actor_id = OS.get_environment("ELFIENEST_E2E_ACTOR_ID")
	_started_at_msec = Time.get_ticks_msec()
	call_deferred("_start_after_project_readiness")


func _start_after_project_readiness() -> void:
	if not await PROJECT_READINESS.wait_until_ready(self):
		_fail("Godot project import/class scan did not become ready")
		return
	var main_scene := load(MAIN_SCENE_PATH) as PackedScene
	if main_scene == null:
		_fail("main scene could not be loaded after project readiness")
		return
	_main = main_scene.instantiate()
	get_root().add_child(_main)
	var nest := _main.get_node_or_null("Nest") as ModularNest
	if nest == null or not nest.visible:
		_fail("visual authority did not expose the real Nest scene")
		return
	if not await _select_requested_camera(nest):
		_fail("requested real-room camera view was not available")
		return
	_observe_until_complete()


func _select_requested_camera(nest: ModularNest) -> bool:
	var requested_view := OS.get_environment(CAMERA_VIEW_ENV).strip_edges()
	if requested_view.is_empty():
		return true
	for _frame in range(120):
		if nest.select_observation_view_named(requested_view):
			_camera_view = requested_view
			return true
		await process_frame
	return false


func _wait_for_rendered_frames(count: int = 3) -> void:
	for _frame in range(count):
		await process_frame


func _observe_until_complete() -> void:
	var timeout_seconds := float(OS.get_environment("ELFIENEST_E2E_GODOT_TIMEOUT_SECONDS"))
	if timeout_seconds <= 0.0:
		timeout_seconds = 180.0
	while Time.get_ticks_msec() - _started_at_msec < int(timeout_seconds * 1000.0):
		await process_frame
		if _main == null:
			_fail("main scene was freed")
			return
		var characters := _main.get_node_or_null("Characters") as Node3D
		if characters == null:
			continue
		_actor = _find_actor(characters)
		if _actor == null:
			continue
		if not _initial_captured:
			_initial_position = _actor.global_position
			if _actor_id.is_empty():
				_actor_id = String(_actor.get("elfie_id"))
			await _wait_for_rendered_frames()
			_initial_captured = _save_screenshot(_initial_path)
			if _initial_captured:
				_log("e2e_initial_position", {
					"actor_id": _actor_id,
					"position": _vector_to_dict(_initial_position),
				})
			continue
		var active_command := String(_actor.get("active_command_id"))
		var moved := _actor.global_position.distance_to(_initial_position) > 0.35
		if moved and active_command.is_empty() and not _final_captured:
			await _wait_for_rendered_frames()
			_final_captured = _save_screenshot(_final_path)
			if _final_captured:
				var report := {
					"status": "passed",
					"actor_id": _actor_id,
					"camera_view": _camera_view,
					"initial_position": _vector_to_dict(_initial_position),
					"final_position": _vector_to_dict(_actor.global_position),
					"distance": _actor.global_position.distance_to(_initial_position),
					"active_command_id": active_command,
				}
				_write_report(report)
				_log("e2e_movement_verified", report)
				# Keep the authoritative Runtime alive while the Python side consumes
				# the terminal outcome and runs the following Brain turn.
				var grace_seconds := float(OS.get_environment("ELFIENEST_E2E_POST_VERIFY_SECONDS"))
				if grace_seconds <= 0.0:
					grace_seconds = 30.0
				await create_timer(grace_seconds).timeout
				quit(0)
				return
		if not active_command.is_empty():
			_log("e2e_motion_active", {
				"actor_id": _actor_id,
				"command_id": active_command,
				"position": _vector_to_dict(_actor.global_position),
			})
	_fail("timed out waiting for the actor to move and settle")


func _find_actor(characters: Node3D) -> Node3D:
	for candidate in characters.get_children():
		if not candidate is Node3D:
			continue
		if _actor_id.is_empty() or String(candidate.get("elfie_id")) == _actor_id:
			return candidate as Node3D
	return null


func _save_screenshot(path: String) -> bool:
	if path.is_empty():
		return false
	var viewport_texture := get_root().get_texture()
	if viewport_texture == null:
		return false
	var image := viewport_texture.get_image()
	if image == null or image.is_empty():
		return false
	return image.save_png(path) == OK


func _write_report(report: Dictionary) -> void:
	if _report_path.is_empty():
		return
	var file := FileAccess.open(_report_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report))


func _fail(reason: String) -> void:
	var report := {"status": "failed", "reason": reason}
	_write_report(report)
	_log("e2e_failed", report)
	quit(1)


func _log(event_name: String, fields: Dictionary) -> void:
	var payload := {"event": event_name}
	for key: Variant in fields:
		payload[key] = fields[key]
	print(JSON.stringify(payload))


func _vector_to_dict(value: Vector3) -> Dictionary:
	return {"x": value.x, "y": value.y, "z": value.z}
