extends SceneTree

var _failed := false


func _init() -> void:
	call_deferred("_run_contract")


func _run_contract() -> void:
	var scene := load("res://characters/fox/fox.tscn") as PackedScene
	var actor := scene.instantiate() as ElfieActor
	actor.install_shared_animations = false
	root.add_child(actor)
	await process_frame
	actor.configure(
		"bone-proportion-contract",
		Vector3.ZERO,
		{
			"bone_scales": {
				"ArmLength": 1.35,
				"LegLength": 0.65,
				"NeckLength": 1.25,
				"HeadScale": 1.2,
			},
		},
	)
	var skeleton := _find_skeleton(actor)
	if skeleton == null:
		_fail("Fox skeleton not found")
		return
	_assert_scale(skeleton, "mixamorig_LeftArm", Vector3(1.0, 1.35, 1.0))
	_assert_scale(skeleton, "mixamorig_LeftForeArm", Vector3(1.0, 1.35, 1.0))
	_assert_scale(skeleton, "mixamorig_LeftUpLeg", Vector3(1.0, 0.65, 1.0))
	_assert_scale(skeleton, "mixamorig_LeftLeg", Vector3(1.0, 0.65, 1.0))
	_assert_scale(skeleton, "mixamorig_Neck", Vector3(1.0, 1.25, 1.0))
	_assert_scale(skeleton, "mixamorig_Head", Vector3(1.2, 0.96, 1.2))
	if _failed:
		quit(1)
		return
	print("Elfie bone proportion contract passed")
	quit()


func _find_skeleton(actor: Node) -> Skeleton3D:
	for node in actor.find_children("*", "Skeleton3D", true, false):
		return node as Skeleton3D
	return null


func _assert_scale(
	skeleton: Skeleton3D,
	bone_name: String,
	expected: Vector3,
) -> void:
	var bone_index := skeleton.find_bone(bone_name)
	if bone_index < 0:
		_fail("Missing bone: %s" % bone_name)
		return
	var actual := skeleton.get_bone_pose_scale(bone_index)
	if not actual.is_equal_approx(expected):
		_fail("%s scale was %s, expected %s" % [bone_name, actual, expected])


func _fail(message: String) -> void:
	_failed = true
	push_error(message)
