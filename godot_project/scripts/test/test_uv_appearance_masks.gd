extends SceneTree

const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")


func _init() -> void:
	for species_id: String in ["dog", "fox"]:
		if not _check_species_mask(species_id):
			push_error("Rejected UV appearance mask route was unexpectedly enabled for %s" % species_id)
			quit(1)
			return
	print("UV_APPEARANCE_MASKS:dog,fox:default-disabled:rejected-experiment")
	quit()


func _check_species_mask(species_id: String) -> bool:
	var validation := SPECIES_CATALOG.validate_species_package(species_id)
	if not bool(validation.get("accepted", false)):
		return false
	var scene := validation.get("scene") as PackedScene
	if scene == null:
		return false
	var instance := scene.instantiate()
	var visual_root := instance.get_node_or_null("VisualRoot") as Node3D
	var collision_shape := instance.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if visual_root == null or collision_shape == null:
		instance.free()
		return false
	var palette := "fox_red" if species_id == "fox" else "cream"
	var secondary := "silver_gray" if species_id == "fox" else "snow_white"
	ACTOR_APPEARANCE.apply(
		visual_root,
		collision_shape,
		{
			"material_parameters": {
				"palette_id": palette,
				"pattern_id": "classic" if species_id == "fox" else "solid",
				"pattern_layout_id": "classic" if species_id == "fox" else "solid",
				"primary_color_id": palette,
				"secondary_color_id": secondary,
				"accent_color_id": secondary,
				"face_mask_color_id": secondary,
				"marking_color_id": secondary,
				"marking_id": "s_glyph",
				"marking_placement": "forehead_center",
				"marking_scale": 0.9,
				"marking_intensity": 1.0,
			},
		},
		species_id,
	)
	var inspected_mesh := false
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null:
			continue
		var material := mesh_instance.get_surface_override_material(0) as ShaderMaterial
		if material == null:
			continue
		inspected_mesh = true
		if material.get_shader_parameter("use_appearance_uv_mask") == true:
			instance.free()
			return false
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			mesh_instance.set_surface_override_material(surface_index, null)
	instance.free()
	return inspected_mesh
