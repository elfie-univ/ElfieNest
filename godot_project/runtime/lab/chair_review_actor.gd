extends ElfieActor
## Audition override only: keep gravity/collision active without idle replacing clips.

var audition := false
var root_motion := false
var _curve: Animation
var _curve_position := -1
var _root_bone := -1
var _root_skeleton: Skeleton3D
var _reference_position := Vector3.ZERO
var _virtual_position := Vector3.ZERO
var _virtual_rotation := Quaternion.IDENTITY
var _elapsed := 0.0
var _total := 0.0
var _playing_key := ""
var _original_shape: Shape3D
var _original_collision := Transform3D.IDENTITY
signal clip_terminal(key: String, accepted: bool, reason: String)
signal precision_terminal(accepted: bool, reason: String)
var _precision := false
var _precision_target := Vector3.ZERO
var _precision_seconds := 0.0
var _seated_shapes: Array[CollisionShape3D] = []
var _sequence_shape: Shape3D
var _sequence_collision := Transform3D.IDENTITY
var seated_shape_cache: Array[Shape3D] = []
var _clip_serial := 0


func use_seated_collision() -> bool:
	if not _seated_shapes.is_empty(): return true
	var shapes := seated_shape_cache
	if shapes.is_empty(): return false
	_sequence_shape = _collision_shape.shape
	_sequence_collision = _collision_shape.transform
	_collision_shape.shape = shapes[0]
	_collision_shape.transform = Transform3D.IDENTITY
	for index in range(1, shapes.size()):
		var collision := CollisionShape3D.new()
		collision.shape = shapes[index]
		add_child(collision)
		_seated_shapes.append(collision)
	return true


func clear_seated_collision() -> void:
	if _sequence_shape == null: return
	for collision: CollisionShape3D in _seated_shapes: collision.free()
	_seated_shapes.clear()
	_collision_shape.shape = _sequence_shape
	_collision_shape.transform = _sequence_collision
	_sequence_shape = null


func walk_precisely(target: Vector3, timeout: float = 8.0) -> void:
	# Short, already navigated docking segment only. No transform assignment:
	# the original walking clip, gravity and body/furniture collisions stay active.
	_finish_navigation()
	audition = false
	_precision_target = target
	_precision_seconds = timeout
	_precision = true


func _precision_step(delta: float) -> void:
	_precision_seconds -= delta
	var offset := _precision_target - global_position
	offset.y = 0.0
	if offset.length() < 0.005 or _precision_seconds <= 0.0:
		_precision = false
		velocity.x = 0.0
		velocity.z = 0.0
		_play_animation("idle")
		precision_terminal.emit(offset.length() < 0.005, "remaining %.4f m" % offset.length())
		return
	var direction := offset.normalized()
	var previous_heading := _visual_root.global_basis
	look_at(global_position - direction, Vector3.UP)
	_animation_runtime.smooth_heading(previous_heading)
	_play_animation("walking")
	var speed := minf(WALK_SPEED, offset.length() / delta)
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed
	velocity.y = 0.0 if is_on_floor() else velocity.y + get_gravity().y * delta
	move_and_slide()


func begin_sequence(body_bottom_y: float) -> void:
	_root_skeleton = _furniture_hips()["skeleton"] as Skeleton3D
	_root_bone = int(_furniture_hips()["bone"])
	_reference_position = _root_skeleton.get_bone_pose_position(_root_bone)
	_virtual_position = _reference_position
	_virtual_rotation = _root_skeleton.get_bone_pose_rotation(_root_bone)
	_original_shape = _collision_shape.shape
	_original_collision = _collision_shape.transform
	# Keep the collider active, fitting the upper body while the downloaded
	# leg poses fold. The chair/environment colliders are never modified.
	var capsule := (_original_shape as CapsuleShape3D).duplicate() as CapsuleShape3D
	var scale_y := absf(_collision_shape.scale.y)
	var top := _collision_shape.position.y + capsule.height * scale_y * 0.5
	var bottom := maxf(0.0, body_bottom_y - global_position.y)
	var height := maxf(capsule.radius * scale_y * 2.0, top - bottom)
	capsule.height = height / scale_y
	_collision_shape.shape = capsule
	_collision_shape.position.y = bottom + height * 0.5
	audition = true
	root_motion = true
	_player_library()


func _player_library() -> void:
	if _animation_player.has_animation_library("motion"):
		_animation_player.remove_animation_library("motion")
	_animation_player.add_animation_library("motion", AnimationLibrary.new())
	_clip_serial = 0


func start_clip(key: String, repeats: int = 1) -> bool:
	var source := _animation_player.get_animation("chair/" + key)
	if source == null: return false
	_curve = source.duplicate(true) as Animation
	var root_path := NodePath("Skeleton3D:" + String(_root_skeleton.get_bone_name(_root_bone)))
	_curve_position = _curve.find_track(root_path, Animation.TYPE_POSITION_3D)
	var rotation_track := _curve.find_track(root_path, Animation.TYPE_ROTATION_3D)
	if _curve_position < 0 or rotation_track < 0: return false
	var first := _curve.position_track_interpolate(_curve_position, 0.0)
	var first_rotation := _curve.rotation_track_interpolate(rotation_track, 0.0)
	var offset := Basis(Vector3.UP, Basis(_virtual_rotation * first_rotation.inverse()).get_euler().y)
	# Constant clip-coordinate composition only. Timings and relative motion
	# remain downloaded; no trajectory is synthesized to reach the furniture.
	for frame in range(_curve.track_get_key_count(_curve_position)):
		var point := _curve.track_get_key_value(_curve_position, frame) as Vector3
		_curve.track_set_key_value(_curve_position, frame, _virtual_position + offset * (point - first))
	for frame in range(_curve.track_get_key_count(rotation_track)):
		var rotation := _curve.track_get_key_value(rotation_track, frame) as Quaternion
		_curve.track_set_key_value(rotation_track, frame, (offset * Basis(rotation)).get_rotation_quaternion())
	_curve.loop_mode = Animation.LOOP_LINEAR if repeats > 1 else Animation.LOOP_NONE
	var displayed := _curve.duplicate(true) as Animation
	# Root displacement drives move_and_collide; it must not also move the skin.
	displayed.remove_track(_curve_position)
	var library := _animation_player.get_animation_library("motion")
	# A new playback identity resets time and retains the preceding clip for
	# the blend. Replacing an active resource named "current" resumes its time.
	_clip_serial += 1
	var playback := "%02d_%s" % [_clip_serial, key]
	library.add_animation(playback, displayed)
	_elapsed = 0.0
	_total = _curve.length * repeats
	_playing_key = key
	_animation_player.play("motion/" + playback, 0.15)
	return true


func end_sequence() -> void:
	clear_seated_collision()
	root_motion = false
	audition = false
	_curve = null
	_collision_shape.shape = _original_shape
	_collision_shape.transform = _original_collision
	var idle := _animation_player.get_animation("idle")
	var path := NodePath("Skeleton3D:" + String(_root_skeleton.get_bone_name(_root_bone)))
	var track := idle.find_track(path, Animation.TYPE_ROTATION_3D)
	if track >= 0:
		var idle_rotation := idle.rotation_track_interpolate(track, 0.0)
		var yaw := Basis(_virtual_rotation * idle_rotation.inverse()).get_euler().y
		rotate_y(yaw)
		_root_skeleton.set_bone_pose_rotation(_root_bone, idle_rotation)
	_play_animation("idle")


func _physics_process(delta: float) -> void:
	if _precision:
		_precision_step(delta)
		return
	if root_motion:
		if _curve != null and _elapsed < _total:
			var step := minf(delta * _animation_player.speed_scale, _total - _elapsed)
			_elapsed += step
			_animation_player.advance(step)
			_root_skeleton.set_bone_pose_position(_root_bone, _reference_position)
			var time := _curve.length if _elapsed >= _total else fmod(_elapsed, _curve.length)
			var next := _curve.position_track_interpolate(_curve_position, time)
			var motion := _root_skeleton.global_basis * (next - _virtual_position)
			var hit := move_and_collide(motion) if motion.length() > 0.000001 else null
			if hit != null and hit.get_remainder().length() > 0.004:
				_elapsed = _total
				_animation_player.pause()
				var obstacle := hit.get_collider() as Node
				var source := String(obstacle.get_meta("source_node", obstacle.name)) if obstacle != null else "unknown"
				clip_terminal.emit(_playing_key, false, "real collision: %s / remainder %.3f m / normal %s" % [source, hit.get_remainder().length(), hit.get_normal()])
				return
			_virtual_position = next
			_virtual_rotation = _root_skeleton.get_bone_pose_rotation(_root_bone)
			if _elapsed >= _total:
				clip_terminal.emit(_playing_key, true, "")
		return
	if not audition:
		super(delta)
		return
	velocity.x = 0.0
	velocity.z = 0.0
	velocity.y = 0.0 if is_on_floor() else velocity.y + get_gravity().y * delta
	move_and_slide()


func _process(delta: float) -> void:
	if root_motion:
		return
	elif audition:
		_animation_player.advance(delta)
	else:
		super(delta)
