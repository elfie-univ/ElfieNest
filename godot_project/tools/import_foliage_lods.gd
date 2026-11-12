@tool
extends EditorScenePostImport
## Import-only, index-only intermediate LOD. No runtime sidecar reads.

static func digest(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

static func inputs_error(source: String, manifest: Dictionary) -> String:
	if source != manifest.get("source_path", ""): return "Source path changed"
	if FileAccess.get_sha256(source) != manifest.get("source_sha256", ""): return "Source fingerprint changed"
	var scenes: Dictionary = manifest.get("scene_sha256", {})
	if scenes.is_empty(): return "Missing instance scale proof"
	for path: String in scenes:
		if FileAccess.get_sha256(path) != scenes[path]: return "Placement fingerprint changed: " + path
	return ""

static func float32_sequence_matches(value: Array, expected: Variant) -> bool:
	if not expected is Array or value.size() != expected.size(): return false
	for component: Variant in expected:
		if not (component is float or component is int) or not is_finite(float(component)): return false
	# Compare native encodings, not double-precision JSON decimal expansions.
	# A one-ULP float32 change still fails; no approximate comparison is used.
	return PackedFloat32Array(value).to_byte_array() == PackedFloat32Array(expected).to_byte_array()

static func field_matches(value: Variant, expected: Variant) -> bool:
	if value is PackedByteArray:
		return expected is Dictionary and value.size() == int(expected.get("bytes", -1)) and digest(value) == expected.get("sha256", "")
	if value is AABB:
		return expected is Array and expected.size() == 2 and expected[0] == "T15" and float32_sequence_matches([value.position.x, value.position.y, value.position.z, value.size.x, value.size.y, value.size.z], expected[1])
	if value is Vector4:
		return expected is Array and expected.size() == 2 and expected[0] == "T50" and float32_sequence_matches([value.x, value.y, value.z, value.w], expected[1])
	if value is float:
		return float32_sequence_matches([value], [expected])
	if value is Array:
		if not expected is Array or value.size() != expected.size(): return false
		for i: int in value.size():
			if not field_matches(value[i], expected[i]): return false
		return true
	return value == expected

static func surface_error(mesh: ArrayMesh, entry: Dictionary, edge: float) -> String:
	if mesh == null or mesh.get_surface_count() != 1 or mesh.get_blend_shape_count() != 0:
		return "Expected one static surface"
	var surfaces: Array = mesh.get("_surfaces")
	var surface: Dictionary = surfaces[0]
	var expected: Dictionary = entry.get("baseline", {})
	var keys := surface.keys()
	keys.sort()
	if keys != expected.get("keys", []): return "Surface fields changed"
	var fields: Dictionary = expected.get("fields", {})
	for key: String in keys:
		# Keep the imported material Resource itself; never replace or reconstruct it.
		if key == "material": continue
		if not fields.has(key) or not field_matches(surface[key], fields[key]):
			return "Surface fingerprint changed: " + key
	var lods: Array = surface.get("lods", [])
	if lods.size() != 4 or edge <= 0.0 or edge >= float(lods[0]): return "Unexpected LOD table"
	var encoded: String = entry.get("indices_hex", "")
	if encoded.length() != 24000: return "Expected exactly 2000 triangles"
	var indices := encoded.hex_decode()
	if indices.size() != 12000 or digest(indices) != entry.get("indices_sha256", ""): return "Candidate fingerprint changed"
	for offset: int in range(0, indices.size(), 2):
		if indices.decode_u16(offset) >= int(surface.vertex_count): return "Candidate index outside original vertex buffer"
	return ""

static func mesh_error(mesh: ArrayMesh, manifest: Dictionary) -> String:
	if mesh == null or mesh.resource_name != manifest.get("mesh_name", ""): return "Mesh identity changed"
	if int(manifest.get("triangles", 0)) != 2000: return "Only the reviewed 2000 level is supported"
	var edge: float = PackedFloat32Array([float(manifest.get("lod_edge", 0.0))])[0]
	var error_bound := float(manifest.get("prototype_error_upper_m", 0.0))
	var stretch := float(manifest.get("world_stretch_upper", 0.0))
	if not is_finite(edge) or error_bound <= 0.0 or error_bound >= 0.007 or stretch <= 0.0 or edge < error_bound * stretch:
		return "LOD edge understates verified error"
	var error := surface_error(mesh, manifest.get("main", {}), edge)
	if not error.is_empty(): return "Main: " + error
	error = surface_error(mesh.shadow_mesh, manifest.get("shadow", {}), edge)
	return "Shadow: " + error if not error.is_empty() else ""

static func append_level(mesh: ArrayMesh, entry: Dictionary, edge: float) -> ArrayMesh:
	var surfaces: Array = mesh.get("_surfaces")
	var surface: Dictionary = surfaces[0].duplicate()
	var lods: Array = [PackedFloat32Array([edge])[0], str(entry.indices_hex).hex_decode()]
	lods.append_array(surface.lods)
	surface.lods = lods
	# _surfaces stores native bytes; no add_surface_from_arrays/re-encoding.
	var result: ArrayMesh = mesh.duplicate(false)
	result.set("_surfaces", [surface])
	return result

static func patched_mesh(mesh: ArrayMesh, manifest: Dictionary) -> ArrayMesh:
	if not mesh_error(mesh, manifest).is_empty(): return null
	var result := append_level(mesh, manifest.main, float(manifest.lod_edge))
	result.shadow_mesh = append_level(mesh.shadow_mesh, manifest.shadow, float(manifest.lod_edge))
	return result

func _post_import(scene: Node) -> Object:
	var source := get_source_file()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(source.get_basename() + ".lods.json"))
	if not parsed is Dictionary:
		push_error("Foliage LOD: missing/invalid sidecar")
		return null
	var manifest: Dictionary = parsed
	var error := inputs_error(source, manifest)
	if not error.is_empty():
		push_error("Foliage LOD: " + error)
		return null
	var target := scene.find_child(str(manifest.node), true, false) as MeshInstance3D
	if target == null:
		push_error("Foliage LOD: source node missing")
		return null
	var original := target.mesh as ArrayMesh
	error = mesh_error(original, manifest)
	if not error.is_empty():
		push_error("Foliage LOD: " + error + "; regenerate/review the sidecar")
		return null
	var replacement := patched_mesh(original, manifest)
	for node: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == original: node.mesh = replacement
	print("FOLIAGE_LOD_IMPORT appended=2000 base=2304 old_lods=840,240 shadow=preserved")
	return scene
