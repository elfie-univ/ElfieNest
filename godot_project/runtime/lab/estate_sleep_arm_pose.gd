extends RefCounted
## Source-length arm folding for the explicit local sleeping preview.
## Apply only to back mode after restoring the saved local arm rotations.
## Rebuild the duvet after this, then capture the local sleep target through
## the existing animation runtime so its next advance does not erase the pose.

static func apply_back(skeleton: Skeleton3D, visual: Node3D) -> Dictionary:
	var hips := _bone(skeleton, "Hips")
	var chest := _bone(skeleton, "Spine2")
	var left := _bone(skeleton, "LeftArm")
	var right := _bone(skeleton, "RightArm")
	if mini(mini(hips, chest), mini(left, right)) < 0:
		return {"error": "required real torso/arm joint missing"}
	var torso := _point(skeleton, chest) - _point(skeleton, hips)
	var down := -torso.normalized()
	var leftward := (_point(skeleton, left) - _point(skeleton, right)).normalized()
	# The existing sleeping VisualRoot rotation maps authored +Z toward the
	# belly-facing side. This avoids guessing a different local axis per arm.
	var front := visual.global_basis.z.normalized()
	var shoulder_half := _point(skeleton, left).distance_to(_point(skeleton, right)) * 0.5
	var result := {}
	for prefix: String in ["Left", "Right"]:
		var arm := _bone(skeleton, prefix + "Arm")
		var elbow := _bone(skeleton, prefix + "ForeArm")
		var hand := _bone(skeleton, prefix + "Hand")
		if mini(arm, mini(elbow, hand)) < 0:
			return {"error": "required real arm chain missing"}
		var outward := leftward * (1.0 if prefix == "Left" else -1.0)
		# Separate paws on the upper abdomen rather than stacking/interlocking.
		# Ratios are a candidate only: actual skinned contact still needs review.
		var target := _point(skeleton, chest) + down * torso.length() * 0.28
		target += outward * shoulder_half * 0.28 + front * torso.length() * 0.18
		result[prefix] = _solve(skeleton, arm, elbow, hand, target, outward + down * 0.35 + front * 0.1)
	return result

static func _solve(skeleton: Skeleton3D, arm: int, elbow: int, hand: int, target: Vector3, bend_hint: Vector3) -> Dictionary:
	var shoulder := _point(skeleton, arm)
	var a := shoulder.distance_to(_point(skeleton, elbow))
	var b := _point(skeleton, elbow).distance_to(_point(skeleton, hand))
	var reach := target - shoulder
	if minf(a, b) < 0.0001 or reach.length() < 0.0001:
		return {"error": "degenerate real arm geometry"}
	var distance := clampf(reach.length(), absf(a - b) + 0.001, a + b - 0.001)
	var direction := reach.normalized()
	var bend := bend_hint - direction * bend_hint.dot(direction)
	if bend.length_squared() < 0.000001:
		return {"error": "ambiguous elbow bend plane"}
	var along := (a * a + distance * distance - b * b) / (2.0 * distance)
	var elbow_target := shoulder + direction * along + bend.normalized() * sqrt(maxf(0.0, a * a - along * along))
	var wrist_target := shoulder + direction * distance
	_swing(skeleton, arm, _point(skeleton, elbow) - shoulder, elbow_target - shoulder)
	_swing(skeleton, elbow, _point(skeleton, hand) - _point(skeleton, elbow), wrist_target - _point(skeleton, elbow))
	return {"elbow": _point(skeleton, elbow), "wrist": _point(skeleton, hand), "requested_wrist": target, "clamped_wrist": wrist_target, "upper_length": a, "fore_length": b}

static func _swing(skeleton: Skeleton3D, bone: int, old_world: Vector3, new_world: Vector3) -> void:
	var world_to_skeleton := skeleton.global_basis.inverse()
	var swing := Basis(Quaternion((world_to_skeleton * old_world).normalized(), (world_to_skeleton * new_world).normalized()))
	var desired := swing * skeleton.get_bone_global_pose(bone).basis
	var parent := skeleton.get_bone_parent(bone)
	var parent_basis := skeleton.get_bone_global_pose(parent).basis if parent >= 0 else Basis.IDENTITY
	# Godot 4 bone poses already contain the imported local rest rotation.
	# Removing rest again rotates the chain twice and misses the wrist target.
	var local := parent_basis.inverse() * desired
	skeleton.set_bone_pose_rotation(bone, local.orthonormalized().get_rotation_quaternion())

static func _point(skeleton: Skeleton3D, bone: int) -> Vector3:
	return skeleton.to_global(skeleton.get_bone_global_pose(bone).origin)

static func _bone(skeleton: Skeleton3D, suffix: String) -> int:
	for prefix: String in ["mixamorig:", "mixamorig_"]:
		var index := skeleton.find_bone(prefix + suffix)
		if index >= 0:
			return index
	return -1
