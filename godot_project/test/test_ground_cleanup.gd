extends SceneTree
## Soil and paving remain separately bound to their unique GLB meshes.

const SCENE := "res://nest/courtyard/overview/courtyard-all/courtyard-layout.scn"
const BINDING := preload("res://nest/assembly/glb_placement.gd")

func _initialize() -> void:
	call_deferred("run")

static func validate(scene: Node3D) -> String:
	# Engine-generated LODs must not change the measured road/soil contacts.
	for asset: String in ["ground/shared-ground", "waterside/lake"]:
		var options := ConfigFile.new()
		var path := "res://nest/courtyard/parts/" + asset + ".glb.import"
		if options.load(path) != OK or options.get_value("params", "meshes/generate_lods", true):
			return "Contact surfaces must use their authored mesh, not automatic LODs"
	var terrain: MeshInstance3D
	var paving: MeshInstance3D
	for node: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		if node.get_parent().get_script()!=BINDING:continue
		var path := str(node.get_meta("v044_path", ""))
		if path.ends_with("COMPLETE Building garden island"): terrain = node
		if path.contains("Fountain connector paving foundation"): paving = node
	if terrain == null or paving == null or terrain.mesh == null or paving.mesh == null:
		return "The soil or independent connector foundation was not bound"
	if terrain.mesh.get_surface_count() != 4 or paving.mesh.get_surface_count() != 1:
		return "Soil contains a former paving/contact-collar surface"
	if terrain.get_parent().library.resource_path!=paving.get_parent().library.resource_path:
		return "Connector paving lost its unique shared ground source"
	var binding := terrain.get_parent()
	if binding.get_script() != BINDING or binding.source_nodes.size() != binding.get_child_count():
		return "Ground source-to-placement correspondence is broken"
	var terrain_index: int = terrain.get_index()
	var materials: Array = binding.material_variants.get(terrain_index, [])
	if materials.size() > 4: return "Stale soil material overrides remain"
	return ""

func run() -> void:
	var scene := (load(SCENE) as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	await process_frame
	var error := validate(scene)
	scene.free()
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	print("GROUND_CLEANUP_BINDING_OK")
	quit(0)
