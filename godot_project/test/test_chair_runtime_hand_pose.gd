extends SceneTree

func _initialize() -> void:call_deferred("run")

func require(ok: bool,message: String) -> bool:
	if not ok:push_error(message);quit(1)
	return ok

func run() -> void:
	var actor := load("res://characters/tovren/tovren.tscn").instantiate() as ElfieActor
	root.add_child(actor)
	actor.configure("runtime-chair-clearance",Vector3.ZERO)
	await process_frame
	actor._furniture_visual_transform=actor._animation_runtime.standing_visual_transform()
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var left := actor._furniture_bone(skeleton,"LeftHand")
	var right := actor._furniture_bone(skeleton,"RightHand")
	var before: Array[Vector3]=[skeleton.to_global(skeleton.get_bone_global_pose(left).origin),skeleton.to_global(skeleton.get_bone_global_pose(right).origin)]
	var rests: Array[Quaternion]=[]
	for name: String in ["LeftForeArm","LeftHand","RightForeArm","RightHand"]:
		rests.append(skeleton.get_bone_pose_rotation(actor._furniture_bone(skeleton,name)))
	if not require(actor._apply_furniture_pose("sitting"),"Runtime Actor must support its real seated pose"):return
	for i in range(2):
		var hand := left if i==0 else right
		var actual := skeleton.to_global(skeleton.get_bone_global_pose(hand).origin)
		print("RUNTIME_CHAIR_HAND index=",i," before=",before[i]," after=",actual," lift=",actual.y-before[i].y)
		if not require(actual.y>before[i].y+0.09,"Ordinary Actor must apply the confirmed forearm lift, not only the Lab replay"):return
	actor._restore_furniture_pose()
	var names := ["LeftForeArm","LeftHand","RightForeArm","RightHand"]
	for i in range(names.size()):
		if not require(skeleton.get_bone_pose_rotation(actor._furniture_bone(skeleton,names[i])).is_equal_approx(rests[i]),"Leaving the chair must restore the original arm pose"):return
	print("PASS runtime chair hand pose: shared forearm clearance and exact restoration")
	quit(0)
