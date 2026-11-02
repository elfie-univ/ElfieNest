extends RefCounted
## Authored sliding-door motion and conservative occupied-volume protection.
## Default-open policy is supplied by the Nest environment owner; no local clock.

const CLOSE_DELAY_SECONDS := 2.0
const SLIDE_SPEED := 2.5
const APPROACH_DISTANCE := 3.0
const SAFETY_MARGIN := 0.05

var _door: Dictionary
var _hold_seconds := 0.0


func _init(door: Dictionary) -> void:
	_door = door


func advance(delta: float, default_open: bool, actors: Array[Node3D]) -> void:
	var nearby := _nearby(actors)
	if nearby:
		_hold_seconds = CLOSE_DELAY_SECONDS
	else:
		_hold_seconds = maxf(0.0, _hold_seconds - maxf(delta, 0.0))
	var target := 1.0 if default_open or nearby or _hold_seconds > 0.0 else 0.0
	var current := float(_door["amount"])
	var amount := move_toward(current, target, maxf(delta, 0.0) * SLIDE_SPEED)
	# Test the full physical door sweep against every supplied body shape.
	# Conservative world bounds may hold the door longer near corners, but
	# never trade away occupied space merely because a proximity sensor clears.
	if amount < current and closing_blocked(amount, actors):
		_hold_seconds = CLOSE_DELAY_SECONDS
		amount = move_toward(current, 1.0, maxf(delta, 0.0) * SLIDE_SPEED)
	_apply(amount)


func closing_blocked(candidate_amount: float, actors: Array[Node3D]) -> bool:
	var body := _door["body"] as StaticBody3D
	var collision := body.get_child(0) as CollisionShape3D
	var debug_bounds := collision.shape.get_debug_mesh().get_aabb()
	var current_bounds := collision.global_transform * debug_bounds
	var frame := _door["closed"] as Transform3D
	frame.origin += (_door["offset"] as Vector3) * candidate_amount
	if frame.basis.determinant() < 0.0:
		frame.basis.x = -frame.basis.x
	var candidate_bounds := (frame * collision.transform) * debug_bounds
	var swept := current_bounds.merge(candidate_bounds).grow(SAFETY_MARGIN)
	for actor in actors:
		if not is_instance_valid(actor):
			continue
		for shape: CollisionShape3D in actor.find_children("*", "CollisionShape3D", true, false):
			if shape.disabled or shape.shape == null:
				continue
			var occupied := shape.global_transform * shape.shape.get_debug_mesh().get_aabb()
			if swept.intersects(occupied):
				return true
	return false


func _nearby(actors: Array[Node3D]) -> bool:
	var center := _door["center"] as Vector3
	for actor in actors:
		if not is_instance_valid(actor):
			continue
		var position := actor.global_position
		if Vector2(position.x - center.x, position.z - center.z).length() < APPROACH_DISTANCE and absf(position.y - (center.y - 1.2)) < 1.5:
			return true
	return false


func _apply(amount: float) -> void:
	_door["amount"] = amount
	var frame := _door["closed"] as Transform3D
	frame.origin += (_door["offset"] as Vector3) * amount
	(_door["mesh"] as Node3D).global_transform = frame
	if frame.basis.determinant() < 0.0:
		frame.basis.x = -frame.basis.x
	(_door["body"] as Node3D).global_transform = frame
