class_name SpeciesCatalog
extends RefCounted


const MANIFEST_FILENAME := "species_manifest.json"
const SHARED_ACTOR_SCRIPT_PATH := "res://characters/shared/elfie_actor.gd"
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
	var directory := DirAccess.open("res://characters")
	if directory == null:
		return catalog
	directory.list_dir_begin()
	while true:
		var entry := directory.get_next()
		if entry.is_empty():
			break
		if not directory.current_is_dir() or entry in ["shared", "animation", "tools"]:
			continue
		var validation := validate_species_package(entry)
		if bool(validation.get("accepted", false)):
			catalog[entry] = validation["scene"]
	directory.list_dir_end()
	return catalog


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
	if int(manifest.get("schema_version", 0)) != 1:
		return _invalid("unsupported_manifest_schema")
	if String(manifest.get("species_id", "")) != species_id:
		return _invalid("manifest_species_mismatch")
	var scene_file := String(manifest.get("scene_file", ""))
	var model_file := String(manifest.get("model_file", ""))
	if scene_file != "%s.tscn" % species_id or model_file != "%s.glb" % species_id:
		return _invalid("invalid_asset_names")
	var scene_path := "%s/%s" % [package_root, scene_file]
	var model_path := "%s/%s" % [package_root, model_file]
	if not ResourceLoader.exists(scene_path) or not ResourceLoader.exists(model_path):
		return _invalid("missing_runtime_asset")
	var scene_source := FileAccess.get_file_as_string(scene_path)
	if scene_source.find(model_path) < 0:
		return _invalid("scene_model_reference_mismatch")
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
	if visual_root == null or visual_root.find_children("*", "MeshInstance3D", true, false).is_empty():
		instance.free()
		return _invalid("missing_visual_mesh")
	if visual_root.find_children("*", "Skeleton3D", true, false).is_empty():
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


static func _string_array(value: Variant) -> Array[String]:
	var result: Array[String] = []
	if not value is Array:
		return result
	for item: Variant in value as Array:
		if item is String:
			result.append(item as String)
	return result


static func _invalid(code: String) -> Dictionary:
	return {"accepted": false, "code": code}
