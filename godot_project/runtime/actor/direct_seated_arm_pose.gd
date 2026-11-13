extends RefCounted
## Relaxed paws beside the thighs, fitted with the original two-bone arms.
const KEYS := preload("res://runtime/actor/chair_dog_leg_keys.gd")
const SOURCE := preload("res://runtime/actor/chair_seated_hand_pose.gd")

static func solve(actor: ElfieActor, rest: Vector3) -> void:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var hips := skeleton.find_bone("mixamorig_Hips")
	var hip := SOURCE._world(skeleton, hips)
	var heading := Basis(Vector3.UP, hip.basis.orthonormalized().get_euler().y)
	for side: String in ["Left", "Right"]:
		var upper := skeleton.find_bone("mixamorig_" + side + "Arm")
		var lower := skeleton.find_bone("mixamorig_" + side + "ForeArm")
		var hand := skeleton.find_bone("mixamorig_" + side + "Hand")
		var tip := skeleton.find_bone("mixamorig_" + side + "HandIndex4")
		var a := SOURCE._world(skeleton, upper).origin
		var b := SOURCE._world(skeleton, lower).origin
		var wrist := SOURCE._world(skeleton, hand)
		var sign_x := signf((heading.inverse() * (a - hip.origin)).x)
		var target := hip.origin + heading * Vector3(sign_x * rest.x, rest.y, rest.z)
		var first := a.distance_to(b)
		var second := b.distance_to(wrist.origin)
		var direction := (target - a).normalized()
		var distance := clampf(a.distance_to(target), absf(first - second) + 0.001, first + second - 0.001)
		target = a + direction * distance
		var along := (first * first + distance * distance - second * second) / (2.0 * distance)
		var pole := heading * Vector3(sign_x, 0, 0.2)
		if actor.species_id == "saevi": pole = heading * Vector3(sign_x*0.3,0,0.8)
		pole = (pole - direction * pole.dot(direction)).normalized()
		var elbow := a + direction * along + pole * sqrt(maxf(0.0, first * first - along * along))
		KEYS._rotate_toward(skeleton, upper, b - a, elbow - a)
		KEYS._rotate_toward(skeleton, lower, SOURCE._world(skeleton, hand).origin - SOURCE._world(skeleton, lower).origin, target - SOURCE._world(skeleton, lower).origin)
		KEYS._set_world_basis(skeleton, hand, wrist.basis)
		var finger := (SOURCE._world(skeleton, tip).origin - SOURCE._world(skeleton, hand).origin).normalized()
		var relaxed := (heading * Vector3(0, -0.85, 0.4)).normalized()
		KEYS._set_world_basis(skeleton, hand, Basis(Quaternion(finger, relaxed)) * SOURCE._world(skeleton, hand).basis)

static func bake(clip: Animation, actor: ElfieActor, rest: Vector3) -> void:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var saved: Array[Transform3D] = []
	for bone in range(skeleton.get_bone_count()): saved.append(skeleton.get_bone_pose(bone))
	var source := clip.duplicate(true) as Animation
	var names: Array[String] = []
	for side: String in ["Left", "Right"]:
		for suffix: String in ["Arm", "ForeArm", "Hand"]:
			var name := "mixamorig_" + side + suffix
			names.append(name)
			var track := clip.find_track(NodePath("Skeleton3D:" + name), Animation.TYPE_ROTATION_3D)
			if track >= 0: clip.remove_track(track)
	var tracks: Array[int] = []
	for name: String in names:
		var track := clip.add_track(Animation.TYPE_ROTATION_3D)
		clip.track_set_path(track, NodePath("Skeleton3D:" + name))
		tracks.append(track)
	for frame in range(int(ceil(clip.length * 30.0)) + 1):
		var time := minf(float(frame) / 30.0, clip.length)
		SOURCE._apply_source(skeleton, source, time)
		solve(actor, rest)
		for i in range(names.size()): clip.rotation_track_insert_key(tracks[i], time, skeleton.get_bone_pose_rotation(skeleton.find_bone(names[i])))
	for bone in range(saved.size()):
		skeleton.set_bone_pose_position(bone, saved[bone].origin)
		skeleton.set_bone_pose_rotation(bone, saved[bone].basis.get_rotation_quaternion())
