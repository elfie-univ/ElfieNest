@tool
extends EditorScenePostImport
## Carry authored optical extensions into the compiled scene, including Web.
## Source-only importer: no runtime GLB reads, color edits or geometry changes.


func _post_import(scene: Node) -> Object:
	var file := FileAccess.open(get_source_file(), FileAccess.READ)
	file.seek(12)
	var length := file.get_32()
	if file.get_32() != 0x4e4f534a:
		push_error("Estate optics source is missing its GLB JSON header")
		return null
	var document := JSON.parse_string(file.get_buffer(length).get_string_from_utf8()) as Dictionary
	file.close()
	var finishes := {}
	var sample_materials := {}
	for material: Dictionary in document.get("materials", []):
		var material_name := str(material.get("name", ""))
		# glTF permits the unlabelled default material. It has no authored
		# optics to bind by name and must not abort an otherwise valid import.
		if material_name.is_empty():
			continue
		sample_materials[material_name] = material
		var extensions: Dictionary = material.get("extensions", {})
		var coat: Dictionary = extensions.get("KHR_materials_clearcoat", {})
		finishes[material_name] = {
			"clearcoat": coat.get("clearcoatFactor", 0.0),
			"clearcoat_roughness": coat.get("clearcoatRoughnessFactor", 0.0),
			"ior": extensions.get("KHR_materials_ior", {}).get("ior", 1.5),
			"transmission": extensions.get("KHR_materials_transmission", {}).get("transmissionFactor", 0.0),
			"sheen": extensions.get("KHR_materials_sheen", {}),
			"iridescence": extensions.get("KHR_materials_iridescence", {}),
		}
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		for surface in range(node.mesh.get_surface_count()):
			var material := node.get_active_material(surface) as BaseMaterial3D
			if material != null and finishes.has(material.resource_name):
				material.set_meta("source_optics", finishes[material.resource_name])
			if material != null and sample_materials.has(material.resource_name):
				# The optical sample additionally inspects complete glTF definitions;
				# production consumes the narrow source_optics values above.
				material.set_meta("m01_reference_optics", sample_materials[material.resource_name])
	return scene
