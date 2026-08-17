extends SceneTree

const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const EXPECTED_SCALE := 0.7


func _init() -> void:
	var dog := DOG_SCENE.instantiate()
	var visual_root := dog.get_node_or_null("VisualRoot") as Node3D
	var collision_shape := dog.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if visual_root == null or collision_shape == null:
		_fail("Dog scene is missing VisualRoot or CollisionShape3D", dog)
		return

	ACTOR_APPEARANCE.apply(
		visual_root,
		collision_shape,
		{"height_scale": 1.0, "build_scale": 1.0},
		"dog",
	)
	var capsule := collision_shape.shape as CapsuleShape3D
	if capsule == null:
		_fail("Dog collision shape is not a CapsuleShape3D", dog)
		return
	var visual_scale_ok := (
		is_equal_approx(visual_root.scale.x, EXPECTED_SCALE)
		and is_equal_approx(visual_root.scale.y, EXPECTED_SCALE)
		and is_equal_approx(visual_root.scale.z, EXPECTED_SCALE)
	)
	if not visual_scale_ok:
		_fail("Dog visual scale was clamped or applied unevenly: %s" % visual_root.scale, dog)
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
			"Dog collision was not calibrated with the authored scene scale: scale=%s position=%s"
			% [collision_shape.scale, collision_shape.position],
			dog,
		)
		return

	print(
		"DOG_TSCN_SCALE: visual=%s collision_scale=%s collision_position=%s"
		% [visual_root.scale, collision_shape.scale, collision_shape.position]
	)
	dog.free()
	quit()


func _fail(message: String, dog: Node) -> void:
	push_error(message)
	dog.free()
	quit(1)
