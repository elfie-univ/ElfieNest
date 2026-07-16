class_name ElfieActor
extends CharacterBody3D

const WALK_SPEED := 1.15
const ARRIVAL_DISTANCE := 0.22
const WANDER_RADIUS_X := 1.7
const WANDER_MIN_Z := -30.0
const WANDER_MAX_Z := -2.0

var elfie_id := ""
var _target_position: Vector3
var _has_target := false
var _wander_clock := 0.0
var _wander_seed := 0
@onready var _animation_player: AnimationPlayer = get_node_or_null("character/AnimationPlayer")


func configure(identity: String, spawn_position: Vector3) -> void:
	elfie_id = identity
	global_position = spawn_position
	_wander_seed = abs(elfie_id.hash())
	_wander_clock = float(_wander_seed % 500) / 100.0
	_play_animation("idle")
	_pick_wander_target()


func set_target_name(target_name: String) -> void:
	var target_hash := abs(target_name.hash())
	_target_position = Vector3(
		- WANDER_RADIUS_X + float(target_hash % 340) / 100.0,
		0.0,
		WANDER_MIN_Z + float((target_hash / 100) % 2600) / 100.0
	)
	_has_target = true


func _physics_process(delta: float) -> void:
	if not _has_target:
		_wander_clock += delta
		if _wander_clock >= 5.0:
			_pick_wander_target()
	if not _has_target:
		velocity = Vector3.ZERO
		_play_animation("idle")
		return

	var offset := _target_position - global_position
	offset.y = 0.0
	if offset.length() <= ARRIVAL_DISTANCE:
		_has_target = false
		velocity = Vector3.ZERO
		_play_animation("idle")
		return

	var direction := offset.normalized()
	velocity = direction * WALK_SPEED
	_play_animation("walking")
	look_at(global_position + direction, Vector3.UP)
	move_and_slide()


func _play_animation(animation_name: String) -> void:
	if _animation_player == null or not _animation_player.has_animation(animation_name):
		return
	if _animation_player.current_animation != animation_name:
		_animation_player.play(animation_name)


func _pick_wander_target() -> void:
	_wander_seed = int(fposmod(float(_wander_seed * 1103515245 + 12345), 2147483647.0))
	var x_value := float(_wander_seed % 340) / 100.0 - WANDER_RADIUS_X
	_wander_seed = int(fposmod(float(_wander_seed * 1103515245 + 12345), 2147483647.0))
	var z_value := WANDER_MIN_Z + float(_wander_seed % 2600) / 100.0
	_target_position = Vector3(x_value, 0.0, z_value)
	_has_target = true
	_wander_clock = 0.0
