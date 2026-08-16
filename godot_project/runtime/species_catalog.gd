class_name SpeciesCatalog
extends RefCounted


const MANIFEST_FILENAME := "species_manifest.json"
const SHARED_ACTOR_SCRIPT_PATH := "res://characters/shared/elfie_actor.gd"
const MANIFEST_SCHEMA_VERSION := 2
const APPEARANCE_PROTOCOL_VERSION := "appearance.v2"
const REQUIRED_NODE_PATHS := [
	"VisualRoot",
	"VisualRoot/character",
	"AnimationPlayer",
	"CollisionShape3D",
]
const REQUIRED_CAPABILITIES := ["movement", "appearance", "portrait", "preview"]
const REQUIRED_ANIMATIONS := [
	"idle",
	"walking",
	"running",
	"jump",
	"twist_dance",
	"left_strafe",
	"left_strafe_walking",
	"left_turn",
	"left_turn_90",
	"right_strafe",
	"right_strafe_walking",
	"right_turn",
	"right_turn_90",
]


static func discover_actor_scenes() -> Dictionary:
	"""Discover only complete species packages, never bare placeholder scenes."""
	var catalog := {}
	for entry: String in discover_package_ids():
		var validation := validate_species_package(entry)
		if bool(validation.get("accepted", false)):
			catalog[entry] = validation["scene"]
	return catalog


static func discover_package_ids() -> Array[String]:
	"""Return every character package directory for dynamic validation."""
	var package_ids: Array[String] = []
	var directory := DirAccess.open("res://characters")
	if directory == null:
		return package_ids
	directory.list_dir_begin()
	while true:
		var entry := directory.get_next()
		if entry.is_empty():
			break
		if directory.current_is_dir() and entry not in ["shared", "animation", "tools"]:
			package_ids.append(entry)
	directory.list_dir_end()
	package_ids.sort()
	return package_ids


static func validate_species_package(species_id: String) -> Dictionary:
	"""Validate the immutable runtime package before publishing a species."""
	if species_id.is_empty() or species_id.contains("/"):
		return _invalid("invalid_species_id")
	var package_root := "res://characters/%s" % species_id
	var manifest_path := "%s/%s" % [package_root, MANIFEST_FILENAME]
	if not FileAccess.file_exists(manifest_path):
		return _invalid("missing_manifest")
	var manifest_value: Variant = JSON.parse_string(
		FileAccess.get_file_as_string(manifest_path)
	)
	if not manifest_value is Dictionary:
		return _invalid("invalid_manifest")
	var manifest := manifest_value as Dictionary
	if int(manifest.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
		return _invalid("unsupported_manifest_schema")
	if String(manifest.get("species_id", "")) != species_id:
		return _invalid("manifest_species_mismatch")
	if String(manifest.get("package_version", "")).is_empty():
		return _invalid("missing_package_version")
	if String(manifest.get("appearance_protocol_version", "")) != APPEARANCE_PROTOCOL_VERSION:
		return _invalid("unsupported_appearance_protocol")
	var scene_file := String(manifest.get("scene_file", ""))
	var model_file := String(manifest.get("model_file", ""))
	if scene_file != "%s.tscn" % species_id or model_file != "%s.glb" % species_id:
		return _invalid("invalid_asset_names")
	var scene_path := "%s/%s" % [package_root, scene_file]
	var model_path := "%s/%s" % [package_root, model_file]
	if not ResourceLoader.exists(scene_path) or not ResourceLoader.exists(model_path):
		return _invalid("missing_runtime_asset")
	# Exported PCKs rewrite imported scene dependencies to generated resource paths;
	# validate the loaded scene and its runtime nodes below instead of source text.
	var scene := load(scene_path) as PackedScene
	if scene == null:
		return _invalid("scene_load_failed")
	var instance := scene.instantiate()
	if instance == null or not instance is CharacterBody3D:
		if instance != null:
			instance.free()
		return _invalid("scene_root_not_character_body")
	if instance.get_script() != load(SHARED_ACTOR_SCRIPT_PATH):
		instance.free()
		return _invalid("scene_actor_script_mismatch")
	if String(instance.get("species_id")) != species_id:
		instance.free()
		return _invalid("scene_species_mismatch")
	var required_nodes := _string_array(manifest.get("required_nodes", []))
	for node_path: String in REQUIRED_NODE_PATHS:
		if not required_nodes.has(node_path) or instance.get_node_or_null(node_path) == null:
			instance.free()
			return _invalid("missing_required_node")
	var visual_root := instance.get_node_or_null("VisualRoot") as Node3D
	var mesh_nodes := []
	var skeleton_nodes := []
	if visual_root != null:
		mesh_nodes = visual_root.find_children("*", "MeshInstance3D", true, false)
		skeleton_nodes = visual_root.find_children("*", "Skeleton3D", true, false)
	if visual_root == null or mesh_nodes.is_empty():
		instance.free()
		return _invalid("missing_visual_mesh")
	if skeleton_nodes.is_empty():
		instance.free()
		return _invalid("missing_skeleton")
	var collision_shape := instance.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if collision_shape == null or collision_shape.shape == null:
		instance.free()
		return _invalid("missing_collision_shape")
	var capabilities := _string_array(manifest.get("required_capabilities", []))
	for capability: String in REQUIRED_CAPABILITIES:
		if not capabilities.has(capability):
			instance.free()
			return _invalid("missing_capability")
	var appearance_bindings: Variant = manifest.get("appearance_bindings", {})
	if not appearance_bindings is Dictionary:
		instance.free()
		return _invalid("invalid_appearance_bindings")
	var bone_bindings: Variant = (appearance_bindings as Dictionary).get("bone_scales", {})
	var blend_bindings: Variant = (appearance_bindings as Dictionary).get("blend_shapes", {})
	var material_bindings: Variant = (appearance_bindings as Dictionary).get("material_parameters", {})
	if not bone_bindings is Dictionary or not blend_bindings is Dictionary or not material_bindings is Dictionary:
		instance.free()
		return _invalid("invalid_appearance_binding_groups")
	for control_name: String in ["HeadScale", "NeckLength", "ArmLength", "LegLength", "HandScale", "PawScale", "TailLength"]:
		var binding: Variant = (bone_bindings as Dictionary).get(control_name, {})
		if not binding is Dictionary:
			instance.free()
			return _invalid("missing_appearance_bone_binding")
		var mode := String((binding as Dictionary).get("mode", ""))
		var bones := _string_array((binding as Dictionary).get("bones", []))
		if mode not in ["uniform", "length"] or bones.is_empty():
			instance.free()
			return _invalid("invalid_appearance_bone_binding")
		for bone_name: String in bones:
			if not _has_bone(skeleton_nodes, bone_name):
				instance.free()
				return _invalid("appearance_bone_not_found")
	for semantic_name: String in (blend_bindings as Dictionary):
		var blend_binding: Variant = (blend_bindings as Dictionary)[semantic_name]
		if not blend_binding is Dictionary:
			instance.free()
			return _invalid("invalid_appearance_blend_binding")
		var shape_names := _string_array((blend_binding as Dictionary).get("shapes", []))
		if shape_names.is_empty() or not _has_blend_shape(mesh_nodes, shape_names):
			instance.free()
			return _invalid("appearance_blend_shape_not_found")
	for semantic_name: String in (material_bindings as Dictionary):
		var material_binding: Variant = (material_bindings as Dictionary)[semantic_name]
		if not material_binding is Dictionary:
			instance.free()
			return _invalid("invalid_appearance_material_binding")
		var material_mode := String((material_binding as Dictionary).get("mode", ""))
		var material_values: Variant = (material_binding as Dictionary).get("values", {})
		if not material_values is Dictionary or (material_values as Dictionary).is_empty():
			instance.free()
			return _invalid("invalid_appearance_material_values")
		for material_value: Variant in (material_values as Dictionary).values():
			if material_mode == "albedo_tint" and not _is_color(material_value):
				instance.free()
				return _invalid("invalid_appearance_material_color")
			if material_mode == "pattern_id" and not (material_value is int or material_value is float):
				instance.free()
				return _invalid("invalid_appearance_material_pattern")
		if material_mode not in ["albedo_tint", "pattern_id"]:
			instance.free()
			return _invalid("unsupported_appearance_material_mode")
	var animations := _string_array(manifest.get("required_animations", []))
	var animation_files: Variant = manifest.get("shared_animation_files", {})
	if not animation_files is Dictionary:
		instance.free()
		return _invalid("invalid_animation_files")
	for animation_name: String in REQUIRED_ANIMATIONS:
		if not animations.has(animation_name):
			instance.free()
			return _invalid("missing_required_animation")
		var source_path := String((animation_files as Dictionary).get(animation_name, ""))
		if (
			source_path.is_empty()
			or not source_path.begins_with("res://characters/animation/")
			or not ResourceLoader.exists(source_path)
		):
			instance.free()
			return _invalid("missing_animation_source")
	instance.free()
	return {"accepted": true, "scene": scene, "manifest": manifest}


static func appearance_bindings(species_id: String) -> Dictionary:
	var validation := validate_species_package(species_id)
	if not bool(validation.get("accepted", false)):
		return {}
	var manifest := validation.get("manifest", {}) as Dictionary
	return manifest.get("appearance_bindings", {}) as Dictionary


static func _string_array(value: Variant) -> Array[String]:
	var result: Array[String] = []
	if not value is Array:
		return result
	for item: Variant in value as Array:
		if item is String:
			result.append(item as String)
	return result


static func _has_bone(nodes: Array, bone_name: String) -> bool:
	for node: Node in nodes:
		var skeleton := node as Skeleton3D
		if skeleton != null and skeleton.find_bone(bone_name) >= 0:
			return true
	return false


static func _has_blend_shape(nodes: Array, shape_names: Array[String]) -> bool:
	for node: Node in nodes:
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for shape_name: String in shape_names:
			if mesh_instance.find_blend_shape_by_name(StringName(shape_name)) >= 0:
				return true
	return false


static func _is_color(value: Variant) -> bool:
	if not value is Array:
		return false
	var values := value as Array
	if values.size() < 3 or values.size() > 4:
		return false
	for component: Variant in values:
		if not (component is int or component is float):
			return false
		if float(component) < 0.0 or float(component) > 1.0:
			return false
	return true


static func _invalid(code: String) -> Dictionary:
	return {"accepted": false, "code": code}
