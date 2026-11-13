@tool
extends "res://nest/assembly/glb_placement.gd"
## Read raw GLB nodes when replaying the pre-migration candidate.

func import_meshes(path: String) -> Dictionary:
	var state := GLTFState.new()
	var document := GLTFDocument.new()
	if document.append_from_file(path, state) != OK: return {}
	var meshes := state.get_meshes()
	var by_name := {}
	# Read all mesh nodes, including alternate bed scenes outside the default scene.
	for node: GLTFNode in state.get_nodes():
		if node.mesh >= 0:
			by_name[node.original_name] = meshes[node.mesh].mesh.get_mesh()
	return by_name
