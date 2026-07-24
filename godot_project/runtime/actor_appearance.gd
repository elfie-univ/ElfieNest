class_name ActorAppearance
extends RefCounted

const BASE_COLLISION_RADIUS := 0.34
const BASE_COLLISION_HEIGHT := 1.72
const BONE_SCALE_CONTROLS := {
	"HeadScale": {
		"mode": "uniform",
		"bones": ["mixamorig_Head"],
	},
	"NeckLength": {
		"mode": "length",
		"bones": ["mixamorig_Neck"],
	},
	"ArmLength": {
		"mode": "length",
		"bones": [
			"mixamorig_LeftArm",
			"mixamorig_LeftForeArm",
			"mixamorig_RightArm",
			"mixamorig_RightForeArm",
		],
	},
	"LegLength": {
		"mode": "length",
		"bones": [
			"mixamorig_LeftUpLeg",
			"mixamorig_LeftLeg",
			"mixamorig_RightUpLeg",
			"mixamorig_RightLeg",
		],
	},
	"HandScale": {
		"mode": "uniform",
		"bones": ["mixamorig_LeftHand", "mixamorig_RightHand"],
	},
	"PawScale": {
		"mode": "uniform",
		"bones": ["mixamorig_LeftFoot", "mixamorig_RightFoot"],
	},
	"TailLength": {
		"mode": "length",
		"bones": ["mixamorig_Tail_Bone"],
	},
}


static func apply(
	visual_root: Node3D,
	collision_shape: CollisionShape3D,
	appearance: Dictionary,
) -> void:
	var height_scale := _appearance_scale(
		appearance.get("height_scale", appearance.get("height", "standard")),
		{"short": 0.92, "standard": 1.0, "tall": 1.08},
	)
	var build_scale := _appearance_scale(
		appearance.get("build_scale", appearance.get("build", "standard")),
		{"slim": 0.92, "standard": 1.0, "plump": 1.08},
	)
	height_scale = clampf(height_scale, 0.85, 1.15)
	build_scale = clampf(build_scale, 0.85, 1.15)
	visual_root.scale = Vector3(build_scale, height_scale, build_scale)

	var capsule := collision_shape.shape.duplicate() as CapsuleShape3D
	capsule.radius = BASE_COLLISION_RADIUS * build_scale
	capsule.height = maxf(
		BASE_COLLISION_HEIGHT * height_scale,
		capsule.radius * 2.0,
	)
	collision_shape.shape = capsule
	collision_shape.position.y = capsule.height * 0.5
	_apply_bone_scales(visual_root, appearance.get("bone_scales", {}))
	_apply_blend_shapes(visual_root, appearance.get("blend_shapes", {}))


static func visual_bounds(visual_root: Node3D) -> AABB:
	var bounds := AABB()
	var has_bounds := false
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		for bone_index in range(skeleton.get_bone_count()):
			var point := skeleton.to_global(
				skeleton.get_bone_global_pose(bone_index).origin
			)
			if has_bounds:
				bounds = bounds.expand(point)
			else:
				bounds = AABB(point, Vector3.ZERO)
				has_bounds = true
	if has_bounds:
		return bounds.grow(0.14)
	return bounds


static func preview_focus_point(visual_root: Node3D, target: String) -> Vector3:
	var bounds := visual_bounds(visual_root)
	if bounds.size.is_zero_approx():
		return visual_root.global_position + Vector3(0.0, 0.9, 0.0)
	if target == "head":
		return Vector3(
			bounds.get_center().x,
			bounds.end.y - bounds.size.y * 0.12,
			bounds.get_center().z,
		)
	return bounds.get_center()


static func _apply_bone_scales(visual_root: Node3D, raw_values: Variant) -> void:
	if not raw_values is Dictionary:
		return
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		for control_name: String in BONE_SCALE_CONTROLS:
			if control_name == "HeadScale" or control_name == "NeckLength":
				continue
			var control: Dictionary = BONE_SCALE_CONTROLS[control_name]
			var factor := clampf(
				float((raw_values as Dictionary).get(control_name, 1.0)),
				0.5,
				1.5,
			)
			var pose_scale := (
				Vector3.ONE * factor
				if control["mode"] == "uniform"
				else Vector3(1.0, factor, 1.0)
			)
			for bone_name: String in control["bones"]:
				var bone_index := skeleton.find_bone(bone_name)
				if bone_index >= 0:
					skeleton.set_bone_pose_scale(bone_index, pose_scale)
		_apply_neck_and_head_scales(skeleton, raw_values as Dictionary)


static func _apply_neck_and_head_scales(
	skeleton: Skeleton3D,
	raw_values: Dictionary,
) -> void:
	var neck_factor := clampf(float(raw_values.get("NeckLength", 1.0)), 0.5, 1.5)
	var head_factor := clampf(float(raw_values.get("HeadScale", 1.0)), 0.5, 1.5)
	var neck_index := skeleton.find_bone("mixamorig_Neck")
	if neck_index >= 0:
		skeleton.set_bone_pose_scale(neck_index, Vector3(1.0, neck_factor, 1.0))
	var head_index := skeleton.find_bone("mixamorig_Head")
	if head_index >= 0:
		# Neck scale is inherited by Head; cancel it on the local length axis.
		skeleton.set_bone_pose_scale(
			head_index,
			Vector3(head_factor, head_factor / neck_factor, head_factor),
		)


static func _apply_blend_shapes(visual_root: Node3D, raw_values: Variant) -> void:
	if not raw_values is Dictionary:
		return
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for shape_name: Variant in (raw_values as Dictionary):
			if mesh_instance.find_blend_shape_by_name(StringName(shape_name)) < 0:
				continue
			mesh_instance.set(
				"blend_shapes/%s" % String(shape_name),
				clampf(float((raw_values as Dictionary)[shape_name]), 0.0, 1.0),
			)


static func _appearance_scale(value: Variant, named_values: Dictionary) -> float:
	if value is float or value is int:
		return float(value)
	return float(named_values.get(String(value), 1.0))
