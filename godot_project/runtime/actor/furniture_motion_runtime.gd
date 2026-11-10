extends RefCounted
## Furniture action lifetime and precise ground approach; authored motion owns sitting.

var _body: CharacterBody3D
var _visual_root: Node3D:
	get: return _body.get_node("VisualRoot") as Node3D
var _animation_runtime: RefCounted:
	get: return _body.get("_animation_runtime")
const WALK_SPEED := ElfieActor.WALK_SPEED

func _init(body: CharacterBody3D) -> void: _body = body
func _finish_navigation() -> void: _body.call("_finish_navigation")
func _play_animation(key: String) -> void: _body.call("_play_animation", key)


signal precision_terminal(accepted: bool, reason: String)
var _precision := false
var _precision_target := Vector3.ZERO
var _precision_seconds := 0.0

func walk_precisely(target: Vector3, timeout: float = 8.0) -> void:
	# Short, already navigated docking segment only. No transform assignment:
	# the original walking clip, gravity and body/furniture collisions stay active.
	_finish_navigation()
	_precision_target = target
	_precision_seconds = timeout
	_precision = true


func _precision_step(delta: float) -> void:
	_precision_seconds -= delta
	var offset := _precision_target - _body.global_position
	offset.y = 0.0
	if offset.length() < 0.005 or _precision_seconds <= 0.0:
		_precision = false
		_body.velocity.x = 0.0
		_body.velocity.z = 0.0
		_play_animation("idle")
		precision_terminal.emit(offset.length() < 0.005, "remaining %.4f m" % offset.length())
		return
	var direction := offset.normalized()
	var previous_heading := _visual_root.global_basis
	_body.look_at(_body.global_position - direction, Vector3.UP)
	_animation_runtime.smooth_heading(previous_heading)
	_play_animation("walking")
	var speed := minf(WALK_SPEED, offset.length() / delta)
	_body.velocity.x = direction.x * speed
	_body.velocity.z = direction.z * speed
	_body.velocity.y = 0.0 if _body.is_on_floor() else _body.velocity.y + _body.get_gravity().y * delta
	_body.move_and_slide()


func physics_frame(delta: float) -> bool:
	if not furniture_cycle_command.is_empty() and not cycle_available(): return true
	if not _precision: return false
	_precision_step(delta)
	return true


var furniture_cycle_command := ""
var cycle_cancelled := false
var cycle_error := ""
var _cycle_deadline := 0

func play_furniture_cycle(marker: Marker3D, anchor_id: String, command_id: String, variant: String, nest: ModularNest) -> Dictionary:
	if not furniture_cycle_command.is_empty(): return {"status":"failed", "reason":"actor_busy"}
	furniture_cycle_command = command_id
	cycle_cancelled = false
	cycle_error = ""
	_cycle_deadline = int(_body.get_meta("furniture_cycle_deadline", Time.get_ticks_msec() + 120000))
	var runner: Node = (load("res://runtime/actor/furniture_cycle.gd") as GDScript).new()
	_body.add_child(runner)
	var result: Dictionary = await runner.run(_body, marker, anchor_id, variant, nest)
	_precision = false
	_body.set_process(true)
	furniture_cycle_command = ""
	runner.queue_free()
	return result

func cancel_furniture_cycle(reason: String) -> void:
	cycle_cancelled = true
	cycle_error = reason
	_precision = false
	precision_terminal.emit(false, reason)

func cycle_available() -> bool:
	if not cycle_cancelled and Time.get_ticks_msec() >= _cycle_deadline:
		cancel_furniture_cycle("deadline_exceeded")
	return not cycle_cancelled
