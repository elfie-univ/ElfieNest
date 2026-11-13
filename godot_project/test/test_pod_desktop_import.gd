extends SceneTree
## Confirm all rooms use their fitted desktops and the shared cabinet.

const FURNITURE := "res://nest/furniture/shared/bedroom/"
const DESKS := FURNITURE + "bedroom-desks.glb"
const CABINET := FURNITURE + "bedroom-cabinet.glb"

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	await process_frame
	var found := 0
	var residents := {}
	var cabinets := 0
	var cabinet_meshes := {}
	const SUPPORT = preload("res://test/split_estate_test_support.gd")
	for placement: Node in SUPPORT.placements(estate):
		var library_path: String = placement.library.resource_path
		if library_path == CABINET:
			if not require(placement.get_child_count() == 7, "A cabinet lost one of its parts"): return
			for index: int in placement.get_child_count():
				var instance := placement.get_child(index) as MeshInstance3D
				var source: String = placement.source_nodes[index]
				if not require(instance != null and instance.mesh != null, "Missing cabinet mesh: " + source): return
				if not require(cabinet_meshes.get(source, instance.mesh) == instance.mesh, "Cabinet mesh was copied: " + source): return
				cabinet_meshes[source] = instance.mesh
			cabinets += 1
		if library_path != DESKS: continue
		var prototypes: Dictionary = placement.import_meshes(placement.library.resource_path)
		for index: int in placement.get_child_count():
			var mesh := placement.get_child(index) as MeshInstance3D
			if mesh == null: continue
			var extras: Dictionary = mesh.get_meta("extras", {})
			if extras.get("piece") != "worktop" or not str(extras.get("module", "")).begins_with("M"): continue
			var key := str(extras.module) + "/" + str(extras.resident)
			var original := preload("res://nest/assembly/glb_placement.gd").select_mesh(prototypes, placement.source_nodes[index], str(mesh.get_meta("v044_path", "")), str(extras.module))
			if not require(original != null and mesh.mesh == original and not mesh.mesh.get_faces().is_empty(), "Desktop lost its current GLB geometry: " + key): return
			var source: Dictionary = original.get_meta("nest_source_extras", {})
			if not require(not residents.has(key) and source.get("component_id") == "desk-top" and not str(source.get("provenance", "")).is_empty(), "Desktop provenance or resident is missing/duplicated: " + key): return
			residents[key] = true
			found += 1
	if not require(found == 32 and residents.size() == 32, "All 32 desktops must use the repaired source"): return
	if not require(cabinets == 32 and cabinet_meshes.size() == 7, "All 32 cabinets must share seven prototype meshes"): return
	print("PASS bedroom imports desktops=", found, " cabinets=", cabinets, " shared_parts=", cabinet_meshes.size())
	estate.free()
	quit()
