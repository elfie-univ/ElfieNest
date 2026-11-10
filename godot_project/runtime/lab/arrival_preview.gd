extends Node
## Lab-only replay of the production presentation; never changes admission facts.
const PRESENTATION := preload("res://runtime/observer/resident_effects.gd")
const TIMING := preload("res://nest/estate/estate_platform_cycle.gd")
var _nest: ModularNest
var _body: ElfieActor
var _effects: Node3D
var _saved: Dictionary = {}
var elapsed := 0.0

func running() -> bool:
	return is_instance_valid(_effects)

func play(nest: ModularNest, body: ElfieActor) -> bool:
	finish()
	if not body.active_command_id.is_empty() or not body.furniture_cycle_command.is_empty(): return false
	_nest = nest
	_body = body
	var collision := body.get_node("CollisionShape3D") as CollisionShape3D
	var agent := body.get_node("NavigationAgent3D") as NavigationAgent3D
	var player := body.get_node("AnimationPlayer") as AnimationPlayer
	_saved = {"transform":body.global_transform,"visible":body.visible,"physics":body.is_physics_processing(),"collision":collision.disabled,"avoidance":agent.avoidance_enabled,"speed":player.speed_scale,"velocity":body.velocity,"animation":player.current_animation,"position":player.current_animation_position}
	_effects = PRESENTATION.new()
	add_child(_effects)
	_effects.setup(nest, body)
	# The temporary event is private to this visual component, not the world snapshot.
	_effects.apply({"hosted":false,"arrival_id":"lab-preview","arrival_started_at":Time.get_unix_time_from_system()})
	_effects.set_process(false)
	if _effects.get("_cycle") == null:
		finish()
		return false
	elapsed = 0.0
	_effects.get("_cycle").sample(elapsed)
	return true

func _process(delta: float) -> void:
	if not running(): return
	if not is_instance_valid(_body):
		_effects.free()
		_effects = null
		return
	if _nest.observer_presentation_paused(): return
	elapsed = minf(elapsed + delta, TIMING.SETTLED_AT)
	_effects.get("_cycle").sample(elapsed)
	if elapsed >= TIMING.SETTLED_AT: finish()

func finish() -> void:
	if not running(): return
	if is_instance_valid(_body):
		_effects.call("_finish_arrival")
		_body.global_transform = _saved.transform
		_body.visible = _saved.visible
		_body.velocity = _saved.velocity
		_body.set_physics_process(_saved.physics)
		(_body.get_node("CollisionShape3D") as CollisionShape3D).disabled = _saved.collision
		(_body.get_node("NavigationAgent3D") as NavigationAgent3D).avoidance_enabled = _saved.avoidance
		var player := _body.get_node("AnimationPlayer") as AnimationPlayer
		player.speed_scale = _saved.speed
		if not str(_saved.animation).is_empty():
			player.play(_saved.animation)
			player.seek(_saved.position, true)
	_effects.free()
	_effects = null
	_body = null

func _exit_tree() -> void:
	finish()
