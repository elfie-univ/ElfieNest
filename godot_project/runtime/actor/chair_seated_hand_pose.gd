extends RefCounted
## Chair-only forearm keys: fold and lift resting fingers clear of the desktop.
## Bone lengths, source clips, body placement and furniture collisions stay intact.

const HAND_INSET_METRES := 0.085
const HAND_LIFT_METRES := 0.14

static func apply_current_pose(actor: ElfieActor) -> bool:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var hips := actor._furniture_bone(skeleton,"Hips")
	var bones: Array[int]=[]
	for side: String in ["Left","Right"]:
		for suffix: String in ["ForeArm","Hand"]:
			var bone := actor._furniture_bone(skeleton,side+suffix)
			if bone<0:return false
			bones.append(bone)
	_lift_hands(skeleton,hips,bones,1.0)
	return true

static func _lift_hands(skeleton: Skeleton3D,hips: int,bones: Array[int],weight: float) -> void:
	for index in [0,2]:
		var forearm := bones[index];var hand := bones[index+1]
		var elbow := _world(skeleton,forearm).origin
		var wrist := _world(skeleton,hand)
		var inward := _world(skeleton,hips).origin-wrist.origin
		inward.y=0.0
		var target := wrist.origin+(inward.normalized()*HAND_INSET_METRES+Vector3.UP*HAND_LIFT_METRES)*weight
		var swing := Basis(Quaternion((wrist.origin-elbow).normalized(),(target-elbow).normalized()))
		_set_world_basis(skeleton,forearm,swing*_world(skeleton,forearm).basis)
		_set_world_basis(skeleton,hand,wrist.basis)


static func bake(clip: Animation, key: String, actor: ElfieActor) -> bool:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var hips := skeleton.find_bone("mixamorig_Hips")
	var bones: Array[int] = []
	for side: String in ["Left", "Right"]:
		for suffix: String in ["ForeArm", "Hand"]:
			var bone := skeleton.find_bone("mixamorig_" + side + suffix)
			if bone < 0:
				push_error("Chair hand clearance requires the original forearm and hand joints")
				return false
			bones.append(bone)
	var saved: Array[Transform3D] = []
	for bone in range(skeleton.get_bone_count()):
		saved.append(skeleton.get_bone_pose(bone))
	var source := clip.duplicate(true) as Animation
	for bone in bones:
		var path := NodePath("Skeleton3D:" + String(skeleton.get_bone_name(bone)))
		var track := clip.find_track(path, Animation.TYPE_ROTATION_3D)
		if track >= 0:
			clip.remove_track(track)
	var tracks: Array[int] = []
	for bone in bones:
		var track := clip.add_track(Animation.TYPE_ROTATION_3D)
		clip.track_set_path(track, NodePath("Skeleton3D:" + String(skeleton.get_bone_name(bone))))
		tracks.append(track)
	for frame in range(int(ceil(clip.length * 30.0)) + 1):
		var time := minf(float(frame) / 30.0, clip.length)
		_apply_source(skeleton, source, time)
		var weight := 1.0
		if key == "sit_down":
			weight = smoothstep(0.25, 0.85, time / clip.length)
		elif key == "stand_up":
			weight = 1.0 - smoothstep(0.15, 0.85, time / clip.length)
		_lift_hands(skeleton,hips,bones,weight)
		for index in range(bones.size()):
			clip.rotation_track_insert_key(tracks[index], time, skeleton.get_bone_pose_rotation(bones[index]))
	for bone in range(saved.size()):
		skeleton.set_bone_pose_position(bone, saved[bone].origin)
		skeleton.set_bone_pose_rotation(bone, saved[bone].basis.get_rotation_quaternion())
	return true


static func _apply_source(skeleton: Skeleton3D, clip: Animation, time: float) -> void:
	for track in range(clip.get_track_count()):
		var path := clip.track_get_path(track)
		if path.get_subname_count() != 1:
			continue
		var bone := skeleton.find_bone(path.get_subname(0))
		if bone < 0:
			continue
		if clip.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			skeleton.set_bone_pose_rotation(bone, clip.rotation_track_interpolate(track, time))
		elif clip.track_get_type(track) == Animation.TYPE_POSITION_3D:
			skeleton.set_bone_pose_position(bone, clip.position_track_interpolate(track, time))


static func _world(skeleton: Skeleton3D, bone: int) -> Transform3D:
	return skeleton.global_transform * skeleton.get_bone_global_pose(bone)


static func _set_world_basis(skeleton: Skeleton3D, bone: int, basis: Basis) -> void:
	var parent := skeleton.get_bone_parent(bone)
	var frame := _world(skeleton, parent).basis if parent >= 0 else skeleton.global_basis
	skeleton.set_bone_pose_rotation(bone, (frame.inverse() * basis).orthonormalized().get_rotation_quaternion())
