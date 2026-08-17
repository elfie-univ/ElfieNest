extends SceneTree

const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var fox := FOX_SCENE.instantiate()
	root.add_child(fox)
	await process_frame
	var visual_root := fox.get_node("VisualRoot") as Node3D
	var collision_shape := fox.get_node("CollisionShape3D") as CollisionShape3D
	ACTOR_APPEARANCE.apply(
		visual_root,
		collision_shape,
		{
			"height_scale": 1.0,
			"build_scale": 1.0,
			"material_parameters": {"palette_id": "red", "pattern_id": "cross"},
		},
		"fox",
	)
	await process_frame
	var shader_count := 0
	var emission_texture_count := 0
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := mesh_instance.get_active_material(surface_index) as ShaderMaterial
			if material == null:
				continue
			shader_count += 1
			if bool(material.get_shader_parameter("use_emission_texture")) and material.get_shader_parameter("emission_texture") != null:
				emission_texture_count += 1
	if shader_count == 0 or emission_texture_count == 0:
		push_error("Fox appearance shader did not preserve the imported emission texture")
		fox.free()
		quit(1)
		return
	print("ACTOR_MATERIAL_PRESERVATION: shaders=%d emission_textures=%d" % [shader_count, emission_texture_count])
	fox.free()
	quit()
