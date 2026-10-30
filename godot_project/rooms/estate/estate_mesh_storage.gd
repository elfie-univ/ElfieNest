extends RefCounted
## Share only byte-identical render geometry; each node keeps its own materials.

static func share_textures(estate: Node3D) -> int:
	var materials := {}
	var signatures := {}
	var shared := {}
	var count := 0
	for node: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == null: continue
		for surface in range(node.mesh.get_surface_count()):
			var material := node.get_active_material(surface)
			if material == null or materials.has(material.get_instance_id()): continue
			materials[material.get_instance_id()] = true
			for property: Dictionary in material.get_property_list():
				if not property.usage & PROPERTY_USAGE_STORAGE: continue
				var texture: Variant = material.get(property.name)
				if not texture is ImageTexture or texture.resource_local_to_scene: continue
				var identity: int = texture.get_instance_id()
				if not signatures.has(identity):
					var pixels: Image = texture.get_image()
					var digest := HashingContext.new()
					digest.start(HashingContext.HASH_SHA256)
					digest.update(var_to_bytes([pixels.get_width(), pixels.get_height(), pixels.get_format(), pixels.has_mipmaps()]))
					digest.update(pixels.get_data())
					signatures[identity] = digest.finish().hex_encode()
				var key: String = signatures[identity]
				if not shared.has(key): shared[key] = texture
				elif shared[key] != texture:
					material.set(property.name, shared[key])
					count += 1
	return count

static func share_geometry(estate: Node3D, importing: bool = false) -> Dictionary:
	var signatures := {}
	var shared := {}
	var count := 0
	var bytes := 0
	for node: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		# Bedding animation retains mesh identity as its rest-pose binding.
		if node.has_meta("estate_bedding_layers") or node.has_meta("estate_bedding_bound"):
			continue
		# MultiMesh prototypes bind materials on the mesh itself while restoring
		# the sidecar. Their material variants must remain separate until then.
		if importing and _is_instance_template(node, estate):
			continue
		var mesh := node.mesh as ArrayMesh
		if mesh == null or mesh.get_blend_shape_count() != 0:
			continue
		var identity := mesh.get_instance_id()
		if not signatures.has(identity):
			signatures[identity] = _signature(mesh)
		var key: String = signatures[identity]
		if not shared.has(key):
			shared[key] = mesh
			continue
		if shared[key] == mesh:
			continue
		var materials: Array[Material] = []
		for surface in range(mesh.get_surface_count()):
			var material := node.get_surface_override_material(surface)
			materials.append(material if material != null else mesh.surface_get_material(surface))
		# Mesh-level materials differ between otherwise identical room modules.
		# Overrides preserve every original binding after sharing the geometry.
		node.mesh = shared[key]
		for surface in range(materials.size()):
			node.set_surface_override_material(surface, materials[surface])
		count += 1
		for surface: Dictionary in mesh.get("_surfaces"):
			for buffer in ["vertex_data", "attribute_data", "skin_data", "index_data"]:
				if surface.has(buffer): bytes += surface[buffer].size()
	return {"meshes_shared": count, "buffer_bytes_shared": bytes}

static func _is_instance_template(node: Node, root: Node) -> bool:
	while node != root:
		if str(node.name).begins_with("__ELFIE_INST_GROUP_"):
			return true
		node = node.get_parent()
	return false

static func _signature(mesh: ArrayMesh) -> String:
	var digest := HashingContext.new()
	digest.start(HashingContext.HASH_SHA256)
	# Retain compressed buffers, every LOD, format, bounds and shadow geometry.
	for surface: Dictionary in mesh.get("_surfaces"):
		var geometry := surface.duplicate()
		geometry.erase("material")
		# Importer labels surfaces with their material name; rendering and
		# collisions use the preserved material override and numeric surface index.
		geometry.erase("name")
		digest.update(var_to_bytes(geometry))
	digest.update(var_to_bytes(mesh.custom_aabb))
	digest.update(var_to_bytes(mesh.lightmap_size_hint))
	for key in mesh.get_meta_list():
		digest.update(var_to_bytes([key, mesh.get_meta(key)]))
	if mesh.shadow_mesh != null:
		digest.update(_signature(mesh.shadow_mesh).to_utf8_buffer())
	return digest.finish().hex_encode()
