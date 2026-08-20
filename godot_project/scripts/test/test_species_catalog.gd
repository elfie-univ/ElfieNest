extends SceneTree

const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")


func _init() -> void:
	var package_ids := SPECIES_CATALOG.discover_package_ids()
	var catalog := SPECIES_CATALOG.discover_actor_scenes()
	if package_ids.is_empty():
		push_error("No Godot species packages were discovered")
		quit(1)
		return
	for species_id: String in package_ids:
		if not catalog.has(species_id) or not catalog[species_id] is PackedScene:
			push_error("Discovered actor catalog is missing %s" % species_id)
			quit(1)
			return
	if catalog.size() != package_ids.size():
		push_error("Discovered actor catalog contains an incomplete species")
		quit(1)
		return
	for species_id: String in package_ids:
		var validation := SPECIES_CATALOG.validate_species_package(species_id)
		if not bool(validation.get("accepted", false)):
			push_error("Species package validation failed for %s: %s" % [species_id, validation])
			quit(1)
			return
		if not _appearance_geometry_changes_runtime(species_id, validation):
			push_error("Appearance application did not change runtime state for %s" % species_id)
			quit(1)
			return
	print("SPECIES_CATALOG_IDS:%s" % JSON.stringify(package_ids))
	print("Complete species catalog contract passed: %s" % ", ".join(catalog.keys()))
	quit()


func _appearance_geometry_changes_runtime(species_id: String, validation: Dictionary) -> bool:
	var scene := validation.get("scene") as PackedScene
	if scene == null:
		return false
	var instance := scene.instantiate()
	var visual_root := instance.get_node_or_null("VisualRoot") as Node3D
	var collision_shape := instance.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if visual_root == null or collision_shape == null:
		if instance != null:
			instance.free()
		return false
	var skeletons := visual_root.find_children("*", "Skeleton3D", true, false)
	if skeletons.is_empty():
		instance.free()
		return false
	var skeleton := skeletons[0] as Skeleton3D
	var head_index := skeleton.find_bone("mixamorig_Head")
	if head_index < 0:
		instance.free()
		return false
	var before_head := skeleton.get_bone_pose_scale(head_index)
	ACTOR_APPEARANCE.apply(
		visual_root,
		collision_shape,
		{
			"height_scale": 1.08,
			"build_scale": 1.08,
			"bone_scales": {"HeadScale": 1.08, "NeckLength": 1.06},
			"material_parameters": _material_parameters(species_id),
		},
		species_id,
	)
	var after_head := skeleton.get_bone_pose_scale(head_index)
	var material_applied := false
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := mesh_instance.get_surface_override_material(surface_index)
			if not material is ShaderMaterial:
				continue
			var shader_material := material as ShaderMaterial
			if (
				shader_material.shader != null
				and not shader_material.shader.code.contains("ALPHA =")
				and shader_material.get_shader_parameter(
					"use_appearance_region_source_texture"
				) == true
				and shader_material.get_shader_parameter(
					"appearance_region_source_texture"
				) != null
				and shader_material.get_shader_parameter("appearance_accent_region_0") == 8
				and shader_material.get_shader_parameter("appearance_accent_region_1") == 10
				and shader_material.get_shader_parameter("appearance_marking_id") == 14
				and shader_material.get_shader_parameter("appearance_marking_placement") == 5
			):
				material_applied = true
			mesh_instance.set_surface_override_material(surface_index, null)
	instance.free()
	return before_head != after_head and material_applied


func _material_parameters(species_id: String) -> Dictionary:
	var primary := "silver_gray"
	var light := "ivory"
	var warm := "golden" if species_id == "fox" else "honey_gold"
	return {
		"palette_id": primary,
		"primary_color_id": primary,
		"marking_id": "heart",
		"marking_placement": "chest",
		"marking_color_id": warm,
		"marking_scale": 0.9,
		"marking_intensity": 0.94,
		"region_0_id": "elbow_cuff_pair",
		"region_0_color_id": light,
		"region_0_intensity": 0.92,
		"region_1_id": "knee_cuff_pair",
		"region_1_color_id": primary,
		"region_1_intensity": 0.92,
		"region_2_id": "none",
		"region_2_color_id": primary,
		"region_2_intensity": 0.0,
	}
