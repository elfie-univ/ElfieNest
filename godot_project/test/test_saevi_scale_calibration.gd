extends SceneTree

const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const SAEVI_SCENE := preload("res://characters/saevi/saevi.tscn")
const EXPECTED_SCALE := 0.7


func _init() -> void:
	var saevi := SAEVI_SCENE.instantiate()
	var visual_root := saevi.get_node_or_null("VisualRoot") as Node3D
	var collision_shape := saevi.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if visual_root == null or collision_shape == null:
		_fail("Saevi scene is missing VisualRoot or CollisionShape3D", saevi)
		return

	ACTOR_APPEARANCE.apply(
		visual_root,
		collision_shape,
		{"height_scale": 1.0, "build_scale": 1.0},
		"saevi",
	)
	var capsule := collision_shape.shape as CapsuleShape3D
	if capsule == null:
		_fail("Saevi collision shape is not a CapsuleShape3D", saevi)
		return
	var visual_scale_ok := (
		is_equal_approx(visual_root.scale.x, EXPECTED_SCALE)
		and is_equal_approx(visual_root.scale.y, EXPECTED_SCALE)
		and is_equal_approx(visual_root.scale.z, EXPECTED_SCALE)
	)
	if not visual_scale_ok:
		_fail("Saevi visual scale was clamped or applied unevenly: %s" % visual_root.scale, saevi)
		return
	var collision_scale_ok := (
		is_equal_approx(collision_shape.scale.x, EXPECTED_SCALE)
		and is_equal_approx(collision_shape.scale.y, EXPECTED_SCALE)
		and is_equal_approx(collision_shape.scale.z, EXPECTED_SCALE)
		and is_equal_approx(capsule.height, 1.72)
		and is_equal_approx(capsule.radius, 0.34)
		and is_equal_approx(collision_shape.position.y, 0.86 * EXPECTED_SCALE)
	)
	if not collision_scale_ok:
		_fail(
			"Saevi collision was not calibrated with the authored scene scale: scale=%s position=%s"
			% [collision_shape.scale, collision_shape.position],
			saevi,
		)
		return

	print(
		"SAEVI_TSCN_SCALE: visual=%s collision_scale=%s collision_position=%s"
		% [visual_root.scale, collision_shape.scale, collision_shape.position]
	)
	saevi.free()
	quit()


func _fail(message: String, saevi: Node) -> void:
	push_error(message)
	saevi.free()
	quit(1)
