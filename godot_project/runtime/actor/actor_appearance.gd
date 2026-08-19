class_name ActorAppearance
extends RefCounted

const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")
const BASE_COLLISION_RADIUS := 0.34
const BASE_COLLISION_HEIGHT := 1.72
const APPEARANCE_SHADER_CODE := """
shader_type spatial;
render_mode diffuse_burley;

uniform sampler2D base_texture : source_color;
uniform bool use_base_texture = false;
uniform sampler2D emission_texture : source_color;
uniform bool use_emission_texture = false;
uniform vec4 emission_color : source_color = vec4(1.0);
uniform vec4 base_color : source_color = vec4(1.0);
uniform vec4 appearance_tint : source_color = vec4(1.0);
uniform int appearance_pattern = 0;

void fragment() {
    vec4 base = base_color;
    if (use_base_texture) {
        base *= texture(base_texture, UV);
    }
    vec3 color = base.rgb * appearance_tint.rgb;
    vec3 emission = vec3(0.0);
    if (use_emission_texture) {
        emission = texture(emission_texture, UV).rgb * emission_color.rgb * appearance_tint.rgb;
    }
    float accent = 0.0;
    if (appearance_pattern == 1) {
        accent = step(0.5, fract(UV.x * 7.0));
    } else if (appearance_pattern == 2) {
        accent = step(0.5, fract(UV.x * 4.0) + fract(UV.y * 4.0));
    } else if (appearance_pattern == 3) {
        accent = step(0.55, abs(fract(UV.x * 3.0) - 0.5));
    }
    color = mix(color, color * vec3(0.48, 0.64, 0.82), accent * 0.42);
    emission = mix(emission, emission * vec3(0.48, 0.64, 0.82), accent * 0.42);
    ALBEDO = color;
    EMISSION = emission;
    ALPHA = base.a;
}
"""


static func apply(
	visual_root: Node3D,
	collision_shape: CollisionShape3D,
	appearance: Dictionary,
	species_id: String = "",
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
	var authored_visual_scale := _authored_scale(visual_root, &"actor_authored_scale")
	visual_root.scale = Vector3(
		authored_visual_scale.x * build_scale,
		authored_visual_scale.y * height_scale,
		authored_visual_scale.z * build_scale,
	)
	var authored_collision_scale := _authored_scale(
		collision_shape,
		&"actor_authored_scale",
	)
	collision_shape.scale = Vector3(
		authored_collision_scale.x * build_scale,
		authored_collision_scale.y * height_scale,
		authored_collision_scale.z * build_scale,
	)
	collision_shape.position.y = (
		BASE_COLLISION_HEIGHT
		* authored_collision_scale.y
		* height_scale
		* 0.5
	)
	var bindings: Dictionary = SPECIES_CATALOG.appearance_bindings(species_id)
	_apply_bone_scales(
		visual_root,
		appearance.get("bone_scales", {}),
		bindings.get("bone_scales", {}),
	)
	_apply_blend_shapes(
		visual_root,
		appearance.get("blend_shapes", {}),
		bindings.get("blend_shapes", {}),
	)
	_apply_material_parameters(
		visual_root,
		appearance.get("material_parameters", {}),
		bindings.get("material_parameters", {}),
	)


static func ground_visual_to_plane(visual_root: Node3D, ground_y: float) -> float:
	var lowest_y := _foot_contact_y(visual_root)
	if lowest_y == INF:
		lowest_y = _mesh_bottom_y(visual_root)
	if lowest_y == INF:
		return 0.0
	var offset := ground_y - lowest_y
	visual_root.global_position.y += offset
	return offset


static func _authored_scale(node: Node3D, metadata_key: StringName) -> Vector3:
	if node.has_meta(metadata_key):
		var stored: Variant = node.get_meta(metadata_key)
		if stored is Vector3:
			return stored
	var authored := node.scale
	node.set_meta(metadata_key, authored)
	return authored


static func _foot_contact_y(visual_root: Node3D) -> float:
	var lowest_y := INF
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		for bone_index in range(skeleton.get_bone_count()):
			var bone_name := skeleton.get_bone_name(bone_index).to_lower()
			if not (
				bone_name.contains("toe_end")
					or bone_name.contains("toeend")
					or bone_name.contains("toe_base")
					or bone_name.contains("toebase")
					or bone_name.ends_with("foot")
			):
				continue
			var foot_point := skeleton.to_global(
				skeleton.get_bone_global_pose(bone_index).origin
			)
			lowest_y = minf(lowest_y, foot_point.y)
	return lowest_y


static func _mesh_bottom_y(visual_root: Node3D) -> float:
	var lowest_y := INF
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var bounds := mesh_instance.get_aabb()
		for x_position in [bounds.position.x, bounds.end.x]:
			for y_position in [bounds.position.y, bounds.end.y]:
				for z_position in [bounds.position.z, bounds.end.z]:
					lowest_y = minf(
						lowest_y,
						mesh_instance.to_global(
							Vector3(x_position, y_position, z_position)
						).y,
					)
	return lowest_y


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
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var mesh_bounds := mesh_instance.global_transform * mesh_instance.get_aabb()
		if has_bounds:
			bounds = bounds.merge(mesh_bounds)
		else:
			bounds = mesh_bounds
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


static func _apply_bone_scales(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var bindings := raw_bindings as Dictionary
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		for control_name: String in bindings:
			if control_name == "HeadScale" or control_name == "NeckLength":
				continue
			if not (raw_values as Dictionary).has(control_name):
				continue
			var control: Variant = bindings[control_name]
			if not control is Dictionary:
				continue
			var factor := clampf(
				float((raw_values as Dictionary).get(control_name, 1.0)),
				0.5,
				1.5,
			)
			var pose_scale := (
				Vector3.ONE * factor
				if String((control as Dictionary).get("mode", "")) == "uniform"
				else Vector3(1.0, factor, 1.0)
			)
			for bone_name: String in _string_array((control as Dictionary).get("bones", [])):
				var bone_index := skeleton.find_bone(bone_name)
				if bone_index >= 0:
					skeleton.set_bone_pose_scale(bone_index, pose_scale)
		_apply_neck_and_head_scales(skeleton, raw_values as Dictionary, bindings)


static func _apply_neck_and_head_scales(
	skeleton: Skeleton3D,
	raw_values: Dictionary,
	bindings: Dictionary,
) -> void:
	if not raw_values.has("NeckLength") and not raw_values.has("HeadScale"):
		return
	var neck_factor := clampf(float(raw_values.get("NeckLength", 1.0)), 0.5, 1.5)
	var head_factor := clampf(float(raw_values.get("HeadScale", 1.0)), 0.5, 1.5)
	var neck_control: Variant = bindings.get("NeckLength", {})
	if neck_control is Dictionary and raw_values.has("NeckLength"):
		for bone_name: String in _string_array((neck_control as Dictionary).get("bones", [])):
			var neck_index := skeleton.find_bone(bone_name)
			if neck_index >= 0:
				skeleton.set_bone_pose_scale(neck_index, Vector3(1.0, neck_factor, 1.0))
	var head_control: Variant = bindings.get("HeadScale", {})
	if head_control is Dictionary and raw_values.has("HeadScale"):
		for bone_name: String in _string_array((head_control as Dictionary).get("bones", [])):
			var head_index := skeleton.find_bone(bone_name)
			if head_index >= 0:
				# Neck scale is inherited by Head; cancel it on the local length axis.
				skeleton.set_bone_pose_scale(
					head_index,
					Vector3(head_factor, head_factor / neck_factor, head_factor),
				)


static func _apply_blend_shapes(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var bindings := raw_bindings as Dictionary
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for semantic_name: Variant in (raw_values as Dictionary):
			var binding: Variant = bindings.get(String(semantic_name), {})
			var shape_names := [String(semantic_name)]
			if binding is Dictionary:
				var configured_names := _string_array((binding as Dictionary).get("shapes", []))
				if not configured_names.is_empty():
					shape_names = configured_names
			for shape_name: String in shape_names:
				if mesh_instance.find_blend_shape_by_name(StringName(shape_name)) < 0:
					continue
				mesh_instance.set(
					"blend_shapes/%s" % shape_name,
					clampf(float((raw_values as Dictionary)[semantic_name]), 0.0, 1.0),
				)


static func _apply_material_parameters(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var bindings := raw_bindings as Dictionary
	var tint := Color.WHITE
	var pattern_id := 0
	var has_material_binding := false
	for semantic_name: String in bindings:
		var binding: Variant = bindings[semantic_name]
		if not binding is Dictionary:
			continue
		var value: Variant = (raw_values as Dictionary).get(semantic_name)
		if value == null:
			continue
		var values: Variant = (binding as Dictionary).get("values", {})
		if not values is Dictionary:
			continue
		var mapped: Variant = (values as Dictionary).get(String(value))
		if mapped == null:
			continue
		var mode: String = String((binding as Dictionary).get("mode", ""))
		if mode == "albedo_tint":
			var color: Variant = _color_value(mapped)
			if color != null:
				tint = _multiply_color(tint, color)
				has_material_binding = true
		elif mode == "pattern_id" and (mapped is int or mapped is float):
			pattern_id = int(mapped)
			has_material_binding = true
	if not has_material_binding:
		return
	var shader := Shader.new()
	shader.code = APPEARANCE_SHADER_CODE
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var source_material: Material = mesh_instance.get_active_material(surface_index)
			var material: ShaderMaterial = ShaderMaterial.new()
			material.shader = shader
			material.set_shader_parameter("appearance_tint", tint)
			material.set_shader_parameter("appearance_pattern", pattern_id)
			if source_material is BaseMaterial3D:
				var base_material := source_material as BaseMaterial3D
				material.set_shader_parameter("base_color", base_material.albedo_color)
				if base_material.albedo_texture != null:
					material.set_shader_parameter("base_texture", base_material.albedo_texture)
					material.set_shader_parameter("use_base_texture", true)
				if base_material.emission_enabled and base_material.emission_texture != null:
					material.set_shader_parameter("emission_texture", base_material.emission_texture)
					material.set_shader_parameter("emission_color", base_material.emission)
					material.set_shader_parameter("use_emission_texture", true)
			mesh_instance.set_surface_override_material(surface_index, material)


static func _color_value(value: Variant) -> Variant:
	if value is Array and (value as Array).size() >= 3:
		var values := value as Array
		return Color(
			float(values[0]),
			float(values[1]),
			float(values[2]),
			float(values[3]) if values.size() > 3 else 1.0,
		)
	return null


static func _multiply_color(left: Color, right: Color) -> Color:
	return Color(left.r * right.r, left.g * right.g, left.b * right.b, left.a * right.a)


static func _string_array(value: Variant) -> Array[String]:
	var result: Array[String] = []
	if not value is Array:
		return result
	for item: Variant in value as Array:
		if item is String:
			result.append(item as String)
	return result


static func _appearance_scale(value: Variant, named_values: Dictionary) -> float:
	if value is float or value is int:
		return float(value)
	return float(named_values.get(String(value), 1.0))
