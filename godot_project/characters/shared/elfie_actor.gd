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
const MAX_STEP_HEIGHT := 0.20
const FURNITURE_CONTACT_DISTANCE := 2.0

@export var species_id := ""
@export var install_shared_animations := true
@export var install_preview_poses := false

var elfie_id := ""
var active_command_id := ""
var _deadline_msec := 0
var _navigation_agent: NavigationAgent3D
var _navigation_path := PackedVector3Array()
var _navigation_path_index := 0
var _blocked_seconds := 0.0
var _contact_cooldowns: Dictionary = {}
var _animation_runtime: RefCounted
var furniture_anchor_id := ""
var _furniture_posture := ""
var _furniture_exit_transform := Transform3D.IDENTITY
var _furniture_visual_transform := Transform3D.IDENTITY
var _furniture_bone_poses: Array[Dictionary] = []

signal navigation_terminal(command_id: String, status: String, reason: String)
signal movement_blocked(command_id: String)
signal tactile_contact(contact: Dictionary)

@onready var _visual_root: Node3D = $VisualRoot
@onready var _collision_shape: CollisionShape3D = $CollisionShape3D
@onready var _animation_player: AnimationPlayer = $AnimationPlayer


func _ready() -> void:
	floor_snap_length = maxf(floor_snap_length, MAX_STEP_HEIGHT + 0.05)
	_navigation_agent = NavigationAgent3D.new()
	_navigation_agent.name = "NavigationAgent3D"
	_navigation_agent.path_desired_distance = 0.18
	_navigation_agent.target_desired_distance = ARRIVAL_DISTANCE
	_navigation_agent.path_height_offset = 0.0
	_navigation_agent.radius = ACTOR_APPEARANCE.BASE_COLLISION_RADIUS
	_navigation_agent.height = ACTOR_APPEARANCE.BASE_COLLISION_HEIGHT
	_navigation_agent.neighbor_distance = 3.0
	_navigation_agent.max_neighbors = 16
	_navigation_agent.time_horizon_agents = 2.0
	_navigation_agent.time_horizon_obstacles = 2.0
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
		install_preview_poses and has_skeleton,
	)


func configure(
	identity: String,
	spawn_position: Vector3,
	appearance: Dictionary = {},
) -> void:
	elfie_id = identity
	global_position = spawn_position
	if install_preview_poses:
		# The preview must start from the GLB bind/rest pose. The shared idle
		# clip is a runtime animation with a different arm position and is not
		# the same visual as the model's authored starting pose.
		_animation_runtime.reset_preview_pose()
	ACTOR_APPEARANCE.apply(_visual_root, _collision_shape, appearance, species_id)
	if not install_preview_poses:
		_play_animation("idle")
		# Sample the imported animation before measuring feet. Its initial hips
		# frame differs from the GLB rest pose; grounding rest first sinks actors.
		_animation_player.advance(0.0)
		ground_visual_to_floor(spawn_position.y)


func prepare_preview() -> void:
	install_shared_animations = false
	install_preview_poses = true


func move_to(
	command_id: String,
	target_position: Vector3,
	deadline_seconds: float,
) -> bool:
	if command_id.is_empty() or not active_command_id.is_empty():
		return false
	if not leave_furniture():
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


func _physics_process(delta: float) -> void:
	if install_preview_poses:
		# Character Lab is a nonphysical pose viewer, not a world authority.
		return
	if not furniture_anchor_id.is_empty():
		velocity = Vector3.ZERO
		_navigation_agent.velocity = Vector3.ZERO
		return
	if is_on_floor():
		velocity.y = 0.0
	else:
		velocity.y += get_gravity().y * delta
	if active_command_id.is_empty():
		velocity.x = 0.0
		velocity.z = 0.0
		_navigation_agent.velocity = Vector3.ZERO
		move_and_slide()
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
		and absf(global_position.y - _navigation_path[_navigation_path_index].y)
			<= MAX_STEP_HEIGHT + 0.05
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
		velocity.x = 0.0
		velocity.z = 0.0
		_navigation_agent.velocity = Vector3.ZERO
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
	velocity.x = safe_velocity.x
	velocity.z = safe_velocity.z
	var previous_position := global_position
	var horizontal_motion := (
		Vector3(velocity.x, 0.0, velocity.z) * get_physics_process_delta_time()
	)
	if not _try_step_up(horizontal_motion):
		move_and_slide()
	_emit_significant_contacts()
	var horizontal_progress := Vector2(
		global_position.x - previous_position.x,
		global_position.z - previous_position.z,
	).length()
	if horizontal_progress < BLOCKED_PROGRESS_EPSILON:
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
	velocity.x = 0.0
	velocity.z = 0.0
	_play_animation("idle")


func _try_step_up(horizontal_motion: Vector3) -> bool:
	if not is_on_floor() or velocity.y > 0.0 or horizontal_motion.is_zero_approx():
		return false
	var forward_hit := KinematicCollision3D.new()
	# Recovery-only tread contacts can stop move_and_slide without producing a
	# forward sweep hit. The raised capsule/support sweeps are authoritative.
	if test_move(global_transform, horizontal_motion, forward_hit, safe_margin) and forward_hit.get_collider() is CharacterBody3D:
		return false
	# Sweep the existing capsule, never set a floor height from a nav waypoint.
	var lift := Vector3.UP * (MAX_STEP_HEIGHT + safe_margin)
	var raised := global_transform
	raised.origin += lift
	var up_hit := KinematicCollision3D.new()
	if test_move(global_transform, lift, up_hit, 0.001, false, 8):
		for index in range(up_hit.get_collision_count()):
			if up_hit.get_normal(index).dot(Vector3.UP) < -0.001:
				return false
		# Initial penetration recovery against a rounded tread edge may report
		# an upward-facing contact even while sweeping away. Verify the raised
		# capsule is really clear instead of treating that contact as a ceiling.
		var clearance := PhysicsShapeQueryParameters3D.new()
		clearance.shape = _collision_shape.shape
		clearance.transform = raised * _collision_shape.transform
		clearance.exclude = [get_rid()]
		clearance.collision_mask = collision_mask
		clearance.margin = 0.001
		if not get_world_3d().direct_space_state.intersect_shape(clearance, 1).is_empty():
			return false
	if test_move(raised, horizontal_motion):
		return false
	raised.origin += horizontal_motion
	var support := KinematicCollision3D.new()
	if not test_move(raised, -lift - Vector3.UP * safe_margin, support, safe_margin):
		return false
	if support.get_collider() is CharacterBody3D:
		return false
	var landing := raised.origin + support.get_travel()
	# On narrow treads the downward capsule can touch the current tread first,
	# even while its nose is blocked by the next riser. Identify the actual top
	# at the capsule's leading edge, without sweeping ahead by another radius
	# (which would incorrectly test two steps at once). All candidate heights
	# remain inside the already verified up/forward/down capsule clearance.
	var capsule := _collision_shape.shape as CapsuleShape3D
	if capsule == null: return false
	var scale := _collision_shape.global_basis.get_scale()
	var radius := capsule.radius * maxf(scale.x, scale.z)
	var edge := global_position + horizontal_motion + horizontal_motion.normalized() * (radius + safe_margin)
	var query := PhysicsRayQueryParameters3D.create(edge + Vector3.UP * (MAX_STEP_HEIGHT + safe_margin), edge - Vector3.UP * safe_margin)
	query.exclude = [get_rid()]
	query.collision_mask = collision_mask
	var tread := get_world_3d().direct_space_state.intersect_ray(query)
	var valid_tread := not tread.is_empty() and not tread["collider"] is CharacterBody3D and (tread["normal"] as Vector3).dot(Vector3.UP) >= cos(get_floor_max_angle())
	if valid_tread:
		var height := (tread["position"] as Vector3).y + safe_margin
		if height > global_position.y and height - global_position.y <= MAX_STEP_HEIGHT + 0.001:
			landing.y = maxf(landing.y, height)
	elif support.get_normal().dot(Vector3.UP) < cos(get_floor_max_angle()):
		return false
	var rise := landing.y - global_position.y
	# safe_margin is collision recovery clearance, not a minimum step height.
	# Edge contact can legitimately advance upward only millimetres per frame.
	if rise <= 0.00001 or rise > MAX_STEP_HEIGHT + 0.001:
		return false
	global_position = landing
	velocity.y = 0.0
	return true


static func furniture_marker_error(marker: Marker3D) -> String:
	if marker == null:
		return "anchor_not_found"
	for key in ["kind", "zone_id", "interaction_posture", "interaction_transform"]:
		if not marker.has_meta(key):
			return "missing_interaction_metadata"
	var kind: Variant = marker.get_meta("kind", null)
	var zone_id: Variant = marker.get_meta("zone_id", null)
	var posture: Variant = marker.get_meta("interaction_posture", null)
	var pose: Variant = marker.get_meta("interaction_transform", null)
	if kind not in ["bed", "chair", "activity"]:
		return "anchor_not_usable"
	if not zone_id is String or String(zone_id).strip_edges().is_empty():
		return "missing_interaction_metadata"
	if not pose is Transform3D or posture not in ["sleeping", "sitting"]:
		return "missing_interaction_metadata"
	if (
		(kind == "bed" and posture != "sleeping")
		or (kind == "chair" and posture != "sitting")
	):
		return "incompatible_interaction_posture"
	var interaction_pose := pose as Transform3D
	if (
		not interaction_pose.is_finite()
		or not interaction_pose.basis.is_equal_approx(interaction_pose.basis.orthonormalized())
	):
		return "invalid_interaction_transform"
	if interaction_pose.basis.determinant() < 0.99:
		return "invalid_interaction_transform"
	if marker.global_position.distance_to(interaction_pose.origin) > FURNITURE_CONTACT_DISTANCE:
		return "interaction_out_of_contact_range"
	return ""


func enter_furniture(marker: Marker3D, anchor_id: String) -> String:
	var error := furniture_marker_error(marker)
	if not error.is_empty():
		return error
	if not active_command_id.is_empty() or not furniture_anchor_id.is_empty():
		return "actor_busy"
	if global_position.distance_to(marker.global_position) > ARRIVAL_DISTANCE * 2.0:
		return "furniture_not_reached"
	var pose := marker.get_meta("interaction_transform") as Transform3D
	if global_position.distance_to(pose.origin) > FURNITURE_CONTACT_DISTANCE:
		return "interaction_out_of_contact_range"
	var posture := String(marker.get_meta("interaction_posture"))
	_furniture_visual_transform = _visual_root.transform
	if not _apply_furniture_pose(posture):
		_restore_furniture_pose()
		return "unsupported_furniture_pose"
	_furniture_exit_transform = global_transform
	global_transform = pose
	# The authored frame is a deck/seat contact, not an actor foot origin.
	# Align the actual posed pelvis using the imported skeleton, not a Python offset.
	var hips := _furniture_hips()
	if hips.is_empty():
		global_transform = _furniture_exit_transform
		_restore_furniture_pose()
		return "unsupported_furniture_pose"
	var skeleton := hips["skeleton"] as Skeleton3D
	var hips_position := skeleton.to_global(
		skeleton.get_bone_global_pose(int(hips["bone"])).origin
	)
	var contact_offset := pose.origin - hips_position
	_visual_root.global_position += contact_offset
	# Keep the navigation/body origin at the authored contact frame. No physics
	# integration occurs while furniture is in use; restore the standing capsule on exit.
	_collision_shape.disabled = true
	furniture_anchor_id = anchor_id
	_furniture_posture = posture
	_navigation_agent.avoidance_enabled = false
	velocity = Vector3.ZERO
	return ""


func observer_present_anchor(marker: Marker3D, anchor_id: String, posture: String) -> String:
	# A semantic completion is not permission to teleport through local geometry.
	# This must never be usable on an authority Actor.
	var presentation: Variant = get_meta("observer_presentation", false)
	if typeof(presentation) != TYPE_BOOL or not bool(presentation):
		return "observer_presentation_only"
	if marker == null or anchor_id.is_empty():
		return "anchor_not_found"
	if posture not in ["idle", "sleeping", "sitting"]:
		return "unsupported_observer_posture"
	if posture != "idle":
		var error := furniture_marker_error(marker)
		if not error.is_empty():
			return error
		if String(marker.get_meta("interaction_posture")) != posture:
			return "incompatible_interaction_posture"
	if global_position.distance_to(marker.global_position) > ARRIVAL_DISTANCE * 2.0:
		return "anchor_not_reached"
	observer_stop_presentation()
	if posture == "idle":
		return ""
	return enter_furniture(marker, anchor_id)


func observer_stop_presentation() -> bool:
	var presentation: Variant = get_meta("observer_presentation", false)
	if typeof(presentation) != TYPE_BOOL or not bool(presentation):
		return false
	cancel_navigation("observer_replay_stopped")
	if not furniture_anchor_id.is_empty():
		# View-only exit restores the saved local approach; no authority clearance
		# decision or terminal event is produced for the actual resident.
		global_transform = _furniture_exit_transform
		_restore_furniture_pose()
		_collision_shape.disabled = false
		furniture_anchor_id = ""
		_furniture_posture = ""
	_navigation_agent.avoidance_enabled = false
	_navigation_agent.velocity = Vector3.ZERO
	velocity = Vector3.ZERO
	set_physics_process(false)
	_play_animation("idle")
	return true


func leave_furniture() -> bool:
	if furniture_anchor_id.is_empty():
		return true
	if not _furniture_exit_is_clear():
		return false
	global_transform = _furniture_exit_transform
	_restore_furniture_pose()
	_collision_shape.disabled = false
	furniture_anchor_id = ""
	_furniture_posture = ""
	_navigation_agent.avoidance_enabled = true
	_play_animation("idle")
	return true


func _furniture_exit_is_clear() -> bool:
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = _collision_shape.shape
	query.transform = _furniture_exit_transform * _collision_shape.transform
	query.collision_mask = collision_mask
	query.exclude = [get_rid()]
	query.margin = 0.001
	return get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()


func _furniture_hips() -> Dictionary:
	for node in _visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		var bone := _furniture_bone(skeleton, "Hips")
		if bone >= 0:
			return {"skeleton": skeleton, "bone": bone}
	return {}


func _apply_furniture_pose(posture: String) -> bool:
	if _animation_player.has_animation("idle"):
		_animation_player.play("idle")
		_animation_player.advance(0.0)
	_animation_player.pause()
	if posture == "sleeping":
		_visual_root.rotate_x(-PI / 2.0)
		return not _furniture_hips().is_empty()
	var hips := _furniture_hips()
	if hips.is_empty():
		return false
	var skeleton := hips["skeleton"] as Skeleton3D
	for part: String in ["LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"]:
		var bone := _furniture_bone(skeleton, part)
		if bone < 0:
			return false
		var bone_rotation := skeleton.get_bone_pose_rotation(bone)
		_furniture_bone_poses.append({
			"skeleton": skeleton, "bone": bone, "rotation": bone_rotation,
		})
		var angle := -PI / 2.0 if part.ends_with("UpLeg") else PI / 2.0
		skeleton.set_bone_pose_rotation(bone, bone_rotation * Quaternion(Vector3.RIGHT, angle))
	return true


func _restore_furniture_pose() -> void:
	_visual_root.transform = _furniture_visual_transform
	for saved: Dictionary in _furniture_bone_poses:
		var skeleton := saved["skeleton"] as Skeleton3D
		skeleton.set_bone_pose_rotation(int(saved["bone"]), saved["rotation"] as Quaternion)
	_furniture_bone_poses.clear()
	_animation_player.playback_active = true
	_play_animation("idle")


static func _furniture_bone(skeleton: Skeleton3D, suffix: String) -> int:
	for prefix: String in ["mixamorig:", "mixamorig_"]:
		var bone := skeleton.find_bone(prefix + suffix)
		if bone >= 0:
			return bone
	return -1


func runtime_posture() -> String:
	if not furniture_anchor_id.is_empty():
		return _furniture_posture
	return "walking" if not active_command_id.is_empty() else "idle"


func _horizontal_distance_to(target: Vector3) -> float:
	return Vector2(global_position.x, global_position.z).distance_to(
		Vector2(target.x, target.z)
	)


func play_runtime_expression(expression: String) -> bool:
	if not leave_furniture():
		return false
	return _animation_runtime.play_expression(expression)


func play_runtime_speech() -> void:
	if not furniture_anchor_id.is_empty():
		# Preserve the seated/lying bones; speech must not restart the idle clip.
		set_meta("speaking", true)
		get_tree().create_timer(0.35).timeout.connect(
			func() -> void: set_meta("speaking", false), CONNECT_ONE_SHOT,
		)
		return
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


func ground_visual_to_floor(ground_y: float) -> float:
	return ACTOR_APPEARANCE.ground_visual_to_plane(_visual_root, ground_y)


func preview_focus_point(target: String) -> Vector3:
	return ACTOR_APPEARANCE.preview_focus_point(_visual_root, target)


func play_preview_intent(intent: Dictionary) -> bool:
	return _animation_runtime.play_preview_intent(intent)


func _play_animation(animation_name: String) -> void:
	_animation_runtime.play(animation_name)
