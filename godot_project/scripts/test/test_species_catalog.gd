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
		if not _appearance_application_changes_runtime(species_id, validation):
			push_error("Appearance application did not change runtime state for %s" % species_id)
			quit(1)
			return
	print("SPECIES_CATALOG_IDS:%s" % JSON.stringify(package_ids))
	print("Complete species catalog contract passed: %s" % ", ".join(catalog.keys()))
	quit()


func _appearance_application_changes_runtime(species_id: String, validation: Dictionary) -> bool:
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
	var palette := "orange_red" if species_id == "fox" else "honey_gold"
	ACTOR_APPEARANCE.apply(
		visual_root,
		collision_shape,
		{
			"height_scale": 1.08,
			"build_scale": 1.08,
			"bone_scales": {"HeadScale": 1.08, "NeckLength": 1.06},
			"material_parameters": {
				"palette_id": palette,
				"pattern_id": "classic" if species_id == "fox" else "solid",
				"pattern_layout_id": "classic" if species_id == "fox" else "solid",
				"primary_color_id": palette,
				"secondary_color_id": "snow_white" if species_id == "dog" else "ivory",
				"accent_color_id": "apricot" if species_id == "dog" else "silver_gray",
				"face_mask_color_id": "snow_white" if species_id == "dog" else "ivory",
				"marking_color_id": "smoky_charcoal" if species_id == "dog" else "smoky_black",
				"marking_id": "s_glyph",
				"marking_placement": "forehead_center",
				"marking_scale": 0.9,
				"marking_intensity": 1.0,
			},
		},
		species_id,
	)
	var after_head := skeleton.get_bone_pose_scale(head_index)
	var material_changed := false
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var candidate_material: Material = mesh_instance.get_surface_override_material(surface_index)
			if not candidate_material is ShaderMaterial:
				continue
			var material := candidate_material as ShaderMaterial
			if material.shader == null:
				continue
			material_changed = (
				int(material.get_shader_parameter("appearance_pattern")) == 0
				and material.get_shader_parameter("use_color_slots") == true
				and int(material.get_shader_parameter("appearance_marking")) == 2
				and material.get_shader_parameter("use_source_fur_texture") == true
				and material.get_shader_parameter("source_fur_texture") != null
				and material.shader.code.contains("region_0_id")
				and material.shader.code.contains("EMISSION =")
			)
			if material_changed:
				break
		if material_changed:
			break
	instance.free()
	return before_head != after_head and material_changed
