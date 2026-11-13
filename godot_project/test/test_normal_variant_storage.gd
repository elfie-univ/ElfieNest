extends SceneTree
## Room-specific duvet directions and shared throw directions both use the GLB binder.
const PLACEMENT = preload("res://nest/assembly/glb_placement.gd")
const PATH = "res://nest/furniture/shared/bedroom/bed-shared.glb"
func _initialize() -> void:
	var library := load(PATH) as PackedScene
	var model := library.instantiate()
	var nodes := {}; var variants := {}; var selected_variants := {}; var checked := 0
	var throw_variants := 0
	for node: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false): nodes[str(node.name)] = node
	var binder := PLACEMENT.new(); binder.library = library
	var meshes: Dictionary = binder.import_meshes(PATH)
	for node: MeshInstance3D in nodes.values():
		var extras: Dictionary = node.get_meta("extras", {})
		if extras.has("normal_variant_of"):
			if not node.has_meta("nest_normal_delta") or node.mesh != nodes[extras.normal_variant_of].mesh:
				push_error("Normal variant still embeds a complete duplicate mesh: " + str(node.name))
				binder.free();model.free();quit(1);return
			variants[str(node.name)] = true
		for module: String in extras.get("nest_normal_variants", {}):
			var choices: Dictionary = extras.nest_normal_variants[module]
			for placement: String in choices:
				var selected: Mesh = PLACEMENT.select_mesh(meshes, str(node.name), placement, module)
				if selected == null or selected != PLACEMENT.select_mesh(meshes, str(node.name), placement, module):
					push_error("Lost or repeatedly rebuilt placement " + placement)
					binder.free();model.free();quit(1);return
				if selected.get_meta("nest_source_library", "") != PATH:
					binder.free();model.free();quit(1);return
				if placement.contains(" | Throw | "): throw_variants += 1
				selected_variants[choices[placement]] = true
				checked += 1
	var shell := "part_00000"
	var shell_path := "Generated/CompleteEstate/CompleteFinal/A | Bed | complete independent pod shell"
	var uses_original: bool = PLACEMENT.select_mesh(meshes, shell, shell_path, "M01") == meshes[shell]
	var throw_path := "Generated/CompleteEstate/CompleteFinal/A | Throw | botanical diagonal folded linen2"
	var uses_shared_throw: bool = PLACEMENT.select_mesh(meshes, "part_00971", throw_path, "M02") == meshes["part_00971"]
	var sample: Mesh = PLACEMENT.select_mesh(meshes, "part_00320", "Generated/CompleteEstate/CompleteFinal/A | Bedding | continuous soft bound edge2", "M02")
	var arrays := sample.surface_get_arrays(0); var found := false
	for i: int in arrays[Mesh.ARRAY_VERTEX].size():
		if arrays[Mesh.ARRAY_VERTEX][i].distance_to(Vector3(-0.455243289, 0.348644435, 0.309910119)) < 0.000001:
			found = arrays[Mesh.ARRAY_NORMAL][i].angle_to(Vector3(0.155622318, 0.987705290, -0.014827116)) < 0.0002
	binder.free();model.free()
	print("NORMAL_VARIANT_STORAGE variants=",variants.size()," placements=",checked," original_normal=",found," direct_reuse=",uses_original, " shared_throw=",uses_shared_throw, " throw_variants=",throw_variants)
	quit(0 if not variants.is_empty() and variants == selected_variants and uses_original and found and uses_shared_throw and throw_variants == 0 else 1)
