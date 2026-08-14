class_name ElfieActor
extends CharacterBody3D

const ACTOR_PATH_PLANNER := preload("res://runtime/actor/actor_path_planner.gd")
const ACTOR_ANIMATION_RUNTIME := preload("res://runtime/actor/actor_animation_runtime.gd")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const WALK_SPEED := 1.15
const ARRIVAL_DISTANCE := 0.22
const BLOCKED_SECONDS := 1.5
const BLOCKED_PROGRESS_EPSILON := 0.0001
const CONTACT_COOLDOWN_MSEC := 1000
const CONTACT_INTENSITY_THRESHOLD := 0.15

@export var species_id := ""
@export var install_shared_animations := true

var elfie_id := ""
var active_command_id := ""
var _deadline_msec := 0
var _navigation_agent: NavigationAgent3D
var _navigation_path := PackedVector3Array()
var _navigation_path_index := 0
var _blocked_seconds := 0.0
var _contact_cooldowns: Dictionary = {}
var _animation_runtime: RefCounted

signal navigation_terminal(command_id: String, status: String, reason: String)
signal movement_blocked(command_id: String)
signal tactile_contact(contact: Dictionary)

@onready var _visual_root: Node3D = $VisualRoot
@onready var _collision_shape: CollisionShape3D = $CollisionShape3D
@onready var _animation_player: AnimationPlayer = $AnimationPlayer


func _ready() -> void:
	_navigation_agent = NavigationAgent3D.new()
	_navigation_agent.name = "NavigationAgent3D"
	_navigation_agent.path_desired_distance = 0.18
	_navigation_agent.target_desired_distance = ARRIVAL_DISTANCE
	_navigation_agent.path_height_offset = 0.0
	_navigation_agent.radius = ACTOR_APPEARANCE.BASE_COLLISION_RADIUS
	_navigation_agent.height = ACTOR_APPEARANCE.BASE_COLLISION_HEIGHT
	_navigation_agent.velocity_computed.connect(_on_avoidance_velocity_computed)
	add_child(_navigation_agent)
	add_to_group(&"runtime_elfie_actors")
	_navigation_agent.avoidance_enabled = true
	_navigation_agent.avoidance_priority = 1.0
	_animation_runtime = ACTOR_ANIMATION_RUNTIME.new()
	var has_skeleton := not _visual_root.find_children("*", "Skeleton3D", true, false).is_empty()
	_animation_runtime.setup(
		self,
		_visual_root,
		_animation_player,
		install_shared_animations and has_skeleton,
	)


func configure(
	identity: String,
	spawn_position: Vector3,
	appearance: Dictionary = {},
) -> void:
	elfie_id = identity
	global_position = spawn_position
	ACTOR_APPEARANCE.apply(_visual_root, _collision_shape, appearance)
	_play_animation("idle")


func prepare_preview() -> void:
	install_shared_animations = false


func move_to(
	command_id: String,
	target_position: Vector3,
	deadline_seconds: float,
) -> bool:
	if command_id.is_empty() or not active_command_id.is_empty():
		return false
	active_command_id = command_id
	_deadline_msec = (
		Time.get_ticks_msec()
		+ maxi(1, roundi(deadline_seconds * 1000.0))
	)
	_navigation_path = ACTOR_PATH_PLANNER.path_with_actor_egress(
		self,
		target_position,
	)
	if _navigation_path.is_empty():
		active_command_id = ""
		_deadline_msec = 0
		return false
	_navigation_path_index = 1 if _navigation_path.size() > 1 else 0
	_navigation_agent.target_position = target_position
	_navigation_agent.avoidance_enabled = true
	_navigation_agent.avoidance_priority = 0.0
	return true


func cancel_navigation(reason: String = "cancelled") -> bool:
	if active_command_id.is_empty():
		return false
	var command_id := active_command_id
	_finish_navigation()
	navigation_terminal.emit(command_id, "cancelled", reason)
	return true


func _physics_process(_delta: float) -> void:
	if active_command_id.is_empty():
		velocity = Vector3.ZERO
		_navigation_agent.velocity = Vector3.ZERO
		_play_animation("idle")
		return
	if Time.get_ticks_msec() >= _deadline_msec:
		var expired_command_id := active_command_id
		_finish_navigation()
		navigation_terminal.emit(
			expired_command_id,
			"failed",
			"deadline_exceeded",
		)
		return
	while (
		_navigation_path_index < _navigation_path.size()
		and _horizontal_distance_to(
			_navigation_path[_navigation_path_index]
		) <= _navigation_agent.path_desired_distance
	):
		_navigation_path_index += 1
	if _navigation_path_index >= _navigation_path.size():
		var completed_command_id := active_command_id
		var final_distance := global_position.distance_to(
			_navigation_agent.target_position
		)
		_finish_navigation()
		navigation_terminal.emit(
			completed_command_id,
			"completed" if final_distance <= ARRIVAL_DISTANCE * 2.0 else "failed",
			"" if final_distance <= ARRIVAL_DISTANCE * 2.0 else "unreachable",
		)
		return

	var next_path_position := _navigation_path[_navigation_path_index]
	var offset := next_path_position - global_position
	offset.y = 0.0
	if offset.is_zero_approx():
		velocity = Vector3.ZERO
		return
	var direction := offset.normalized()
	_play_animation("walking")
	# 导入物种模型以 +Z 为视觉前方，而 Node3D.look_at 对齐的是 -Z。
	# 因此看向反方向，使视觉朝向与物理速度一致，避免倒着行走。
	look_at(global_position - direction, Vector3.UP)
	_navigation_agent.velocity = direction * WALK_SPEED


func _on_avoidance_velocity_computed(safe_velocity: Vector3) -> void:
	if active_command_id.is_empty():
		return
	velocity = safe_velocity
	var previous_position := global_position
	move_and_slide()
	_emit_significant_contacts()
	if global_position.distance_to(previous_position) < BLOCKED_PROGRESS_EPSILON:
		_blocked_seconds += get_physics_process_delta_time()
	else:
		_blocked_seconds = 0.0
	if _blocked_seconds >= BLOCKED_SECONDS:
		var blocked_command_id := active_command_id
		movement_blocked.emit(blocked_command_id)
		_finish_navigation()
		navigation_terminal.emit(blocked_command_id, "failed", "movement_blocked")


func _finish_navigation() -> void:
	active_command_id = ""
	_deadline_msec = 0
	_blocked_seconds = 0.0
	_navigation_path = PackedVector3Array()
	_navigation_path_index = 0
	_navigation_agent.avoidance_priority = 1.0
	velocity = Vector3.ZERO
	_play_animation("idle")


func _horizontal_distance_to(target: Vector3) -> float:
	return Vector2(global_position.x, global_position.z).distance_to(
		Vector2(target.x, target.z)
	)


func play_runtime_expression(expression: String) -> bool:
	return _animation_runtime.play_expression(expression)


func play_runtime_speech() -> void:
	_animation_runtime.play_speech()


func _emit_significant_contacts() -> void:
	var now := Time.get_ticks_msec()
	for collision_index in range(get_slide_collision_count()):
		var collision := get_slide_collision(collision_index)
		var collider := collision.get_collider()
		if collider == null:
			continue
		var source_id := String((collider as Node).name)
		if collider is ElfieActor:
			source_id = (collider as ElfieActor).elfie_id
		var cooldown_key := "%s:%s" % [elfie_id, source_id]
		var local_normal := global_basis.inverse() * collision.get_normal()
		var intensity := clampf(
			collision.get_normal().dot(-velocity.normalized()),
			0.0,
			1.0,
		)
		if intensity < CONTACT_INTENSITY_THRESHOLD:
			continue
		if now < int(_contact_cooldowns.get(cooldown_key, 0)):
			continue
		_contact_cooldowns[cooldown_key] = now + CONTACT_COOLDOWN_MSEC
		var direction := "front"
		if absf(local_normal.x) > absf(local_normal.z):
			direction = "left" if local_normal.x > 0.0 else "right"
		elif local_normal.z < 0.0:
			direction = "back"
		tactile_contact.emit({
			"contact_kind": "actor" if collider is ElfieActor else "world",
			"source_semantic_id": source_id,
			"direction": direction,
			"intensity": intensity,
			})


func visual_bounds() -> AABB:
	return ACTOR_APPEARANCE.visual_bounds(_visual_root)


func preview_focus_point(target: String) -> Vector3:
	return ACTOR_APPEARANCE.preview_focus_point(_visual_root, target)


func play_preview_intent(intent: Dictionary) -> bool:
	return _animation_runtime.play_preview_intent(intent)


func _play_animation(animation_name: String) -> void:
	_animation_runtime.play(animation_name)
