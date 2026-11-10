extends RefCounted
## Six real deform joints on the Tovren rig.
## FK keeps every authored segment length and the root attachment fixed.
var actor: ElfieActor
var skeleton: Skeleton3D
var bones: Array[int] = []
var neutral: Array[Transform3D] = []
var tangents: Array[Vector3] = []
var angles := PackedFloat32Array()
var seated_angles := PackedFloat32Array()
var seated_weight := 0.0
var rest_length := 0.0

func bind(body: ElfieActor, rig: Skeleton3D, profile: Resource) -> String:
	actor = body
	skeleton = rig
	angles = profile.get_meta("tail_joint_angles") as PackedFloat32Array
	seated_angles = profile.get_meta("tail_seated_joint_angles") as PackedFloat32Array
	if actor.species_id == "saevi":
		# The fox's wider tail rises at its root rather than extending into
		# the chair back before turning upward like the narrower dog tail.
		angles = PackedFloat32Array([75,15,5,0,0,-5])
		seated_angles = angles.duplicate()
	for i in range(6):
		var bone := skeleton.find_bone("Tail_%02d" % (i + 1))
		if bone < 0: return "six_joint_tail_missing"
		bones.append(bone)
		neutral.append(skeleton.get_bone_pose(bone))
	if angles.size() != bones.size() or seated_angles.size() != bones.size(): return "six_joint_tail_angles_missing"
	skeleton.force_update_all_bone_transforms()
	for i in range(5):
		var world := skeleton.global_transform * skeleton.get_bone_global_pose(bones[i])
		var next := skeleton.to_global(skeleton.get_bone_global_pose(bones[i + 1]).origin)
		tangents.append(world.basis.inverse() * (next - world.origin))
		rest_length += world.origin.distance_to(next)
	tangents.append(tangents.back())
	return ""

func apply(weight: float) -> void:
	# The body clip drives the pelvis. Child tail transforms are recomputed
	# against that current parent, so sitting cannot turn an old world-space
	# tail rotation into a rotation through the torso.
	for i in range(bones.size()):
		skeleton.set_bone_pose_position(bones[i], neutral[i].origin)
		skeleton.set_bone_pose_rotation(bones[i], neutral[i].basis.get_rotation_quaternion())
	for i in range(bones.size()):
		var bone := bones[i]
		var world := skeleton.global_transform * skeleton.get_bone_global_pose(bone)
		var current := (world.basis * tangents[i]).normalized()
		var angle := deg_to_rad(lerpf(angles[i], seated_angles[i], clampf(seated_weight, 0.0, 1.0)))
		var target := actor.global_basis * Vector3(0.0, cos(angle), -sin(angle))
		var desired := Basis(Quaternion(current, target)) * world.basis
		var parent := skeleton.get_bone_parent(bone)
		var parent_world := skeleton.global_transform * skeleton.get_bone_global_pose(parent)
		var local := (parent_world.basis.inverse() * desired).orthonormalized().get_rotation_quaternion()
		var original := neutral[i].basis.get_rotation_quaternion()
		skeleton.set_bone_pose_rotation(bone, original.slerp(local, clampf(weight, 0.0, 1.0)))

func root_position() -> Vector3:
	return actor.to_local(skeleton.to_global(skeleton.get_bone_global_pose(bones[0]).origin))

func measurements() -> Dictionary:
	var points: Array[Vector3] = []
	for bone: int in bones:
		points.append(skeleton.to_global(skeleton.get_bone_global_pose(bone).origin))
	var length := 0.0
	var bend := 0.0
	for i in range(points.size() - 1):
		length += points[i].distance_to(points[i + 1])
		if i > 0:
			bend += (points[i] - points[i - 1]).angle_to(points[i + 1] - points[i])
	return {"deform_joints": bones.size(), "rest_length": rest_length, "posed_length": length, "bend_radians": bend}

func neutral_error() -> float:
	var error := 0.0
	for i in range(bones.size()):
		var actual := skeleton.get_bone_pose(bones[i])
		error = maxf(error, actual.origin.distance_to(neutral[i].origin))
		error = maxf(error, actual.basis.get_rotation_quaternion().angle_to(neutral[i].basis.get_rotation_quaternion()))
	return error
