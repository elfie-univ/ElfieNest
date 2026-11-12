extends SceneTree
## Run after the owner reimports forest-foliage.glb; no test-driven reimport.
const IMPORTER := preload("res://tools/import_foliage_lods.gd")
const SOURCE := "res://nest/courtyard/parts/forest/forest-foliage.glb"
var failures: Array[String] = []

func check(value: bool, message: String) -> void:
	if not value:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	call_deferred("run")

func test_float32_fingerprints() -> void:
	# JSON parsing can differ in the last double digit while encoding the same
	# native float32. Accept that encoding only, not an epsilon neighborhood.
	var parsed: Array = JSON.parse_string("[1.250000000000001, -2.5, 0.5, 4.0, 8.0, 16.0]")
	var bounds := AABB(Vector3(1.25, -2.5, 0.5), Vector3(4, 8, 16))
	check(parsed[0] != 1.25, "Fixture actually differs at double precision")
	check(IMPORTER.field_matches(bounds, ["T15", parsed]), "AABB compares exact native float32 encodings")
	check(IMPORTER.field_matches(Vector4(1.25, -2.5, 0.5, 4), ["T50", parsed.slice(0, 4)]), "Vector4 compares exact native float32 encodings")
	check(IMPORTER.field_matches([1.25], [parsed[0]]), "LOD scalar compares exact native float32 encoding")
	var changed := parsed.duplicate()
	changed[0] = 1.25 + 1.0 / 8388608.0
	check(not IMPORTER.field_matches(bounds, ["T15", changed]), "AABB rejects one float32 ULP")
	check(not IMPORTER.field_matches(Vector4(1.25, -2.5, 0.5, 4), ["T50", changed.slice(0, 4)]), "Vector4 rejects one float32 ULP")
	check(not IMPORTER.field_matches([1.25], [changed[0]]), "LOD rejects one float32 ULP")
	var bytes := PackedByteArray([1, 2, 3, 4])
	var expected := {"bytes": bytes.size(), "sha256": IMPORTER.digest(bytes)}
	check(IMPORTER.field_matches(bytes, expected), "Exact buffer fingerprint accepted")
	bytes[0] = 0
	check(not IMPORTER.field_matches(bytes, expected), "One changed buffer bit still rejected")

func without_candidate(mesh: ArrayMesh) -> ArrayMesh:
	var surfaces: Array = mesh.get("_surfaces")
	var surface: Dictionary = surfaces[0].duplicate()
	surface.lods = surface.lods.slice(2)
	var result: ArrayMesh = mesh.duplicate(false)
	result.set("_surfaces", [surface])
	if mesh.shadow_mesh != null:
		result.shadow_mesh = without_candidate(mesh.shadow_mesh)
	return result

func compare_preserved(before: ArrayMesh, after: ArrayMesh, label: String) -> void:
	var a: Array = before.get("_surfaces")
	var b: Array = after.get("_surfaces")
	check(a.size() == b.size(), label + " surface count")
	for i: int in a.size():
		check(a[i].keys() == b[i].keys(), label + " every surface field retained")
		for key: Variant in a[i]:
			if key == "lods":
				check(var_to_bytes(a[i][key]) == var_to_bytes(b[i][key].slice(2)), label + " all old LOD bytes/edges exact")
			elif key == "material":
				check(a[i][key] == b[i][key], label + " material identity")
			else:
				check(var_to_bytes(a[i][key]) == var_to_bytes(b[i][key]), label + " exact " + str(key))
	check(before.custom_aabb == after.custom_aabb, label + " custom bounds")
	check(before.lightmap_size_hint == after.lightmap_size_hint, label + " lightmap size")
	check(before.resource_name == after.resource_name, label + " name")
	check(before.get_blend_shape_count() == after.get_blend_shape_count(), label + " blend shapes")
	check(before.blend_shape_mode == after.blend_shape_mode, label + " blend mode")
	for key: StringName in before.get_meta_list():
		check(before.get_meta(key) == after.get_meta(key), label + " metadata " + str(key))
	if before.shadow_mesh != null:
		check(after.shadow_mesh != null, label + " shadow retained")
		compare_preserved(before.shadow_mesh, after.shadow_mesh, label + " shadow")

func run() -> void:
	test_float32_fingerprints()
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SOURCE.get_basename() + ".lods.json"))
	check(IMPORTER.inputs_error(SOURCE, manifest).is_empty(), "Source and placement fingerprints current")
	var packed := load(SOURCE) as PackedScene
	check(packed != null, "Formal imported PackedScene exists")
	if packed == null:
		finish()
		return
	var scene := packed.instantiate()
	var target := scene.find_child("part_00006", true, false) as MeshInstance3D
	check(target != null, "Formal part_00006 exists")
	if target == null:
		scene.free()
		finish()
		return
	var imported := target.mesh as ArrayMesh
	for pair: Array in [[imported, manifest.main], [imported.shadow_mesh, manifest.shadow]]:
		var mesh: ArrayMesh = pair[0]
		var surfaces: Array = mesh.get("_surfaces")
		var lods: Array = surfaces[0].lods
		check(lods.size() == 6, "Formal import has exactly new 2000 plus original 840/240 LODs")
		if lods.size() != 6:
			scene.free()
			finish()
			return
		# Serialization rounds the conservative edge to float32; generator rounds upward.
		check(lods[0] >= manifest.world_stretch_upper * manifest.prototype_error_upper_m, "Serialized edge never understates certified error")
		check(IMPORTER.field_matches(lods[0], manifest.lod_edge), "New edge equals sidecar float32 encoding")
		check(lods[1].size() == 12000 and lods[1].hex_encode() == pair[1].indices_hex, "Exact mapped 2000-triangle buffer")
		check(surfaces[0].index_count == 6912, "Near-view base remains 2304 triangles")
	var baseline := without_candidate(imported)
	check(IMPORTER.mesh_error(baseline, manifest).is_empty(), "Removing only new pair exactly matches uncandidated buffer/field/LOD fingerprints")
	var patched: ArrayMesh = IMPORTER.patched_mesh(baseline, manifest)
	check(patched != null, "Baseline can be patched")
	if patched != null:
		compare_preserved(baseline, patched, "main")
		compare_preserved(baseline, imported, "formal")
		check(IMPORTER.mesh_error(baseline, manifest).is_empty(), "Patching leaves baseline untouched")
	check(not IMPORTER.mesh_error(imported, manifest).is_empty(), "Already patched mesh rejected; no duplicate level")
	var stale := manifest.duplicate(true)
	stale.source_sha256 = "stale"
	check(not IMPORTER.inputs_error(SOURCE, stale).is_empty(), "Stale source rejected")
	stale = manifest.duplicate(true)
	stale.scene_sha256[stale.scene_sha256.keys()[0]] = "stale"
	check(not IMPORTER.inputs_error(SOURCE, stale).is_empty(), "Stale placement scale proof rejected")
	for field: String in ["vertex_data", "attribute_data", "index_data"]:
		stale = manifest.duplicate(true)
		stale.main.baseline.fields[field].sha256 = "stale"
		check(IMPORTER.patched_mesh(baseline, stale) == null, "Reject changed " + field)
	stale = manifest.duplicate(true)
	stale.shadow.baseline.fields.lods[1].sha256 = "stale"
	check(IMPORTER.patched_mesh(baseline, stale) == null, "Reject changed shadow LOD")
	stale = manifest.duplicate(true)
	stale.main.indices_hex = "ffff" + stale.main.indices_hex.substr(4)
	check(IMPORTER.patched_mesh(baseline, stale) == null, "Reject corrupted candidate")
	stale.main.indices_sha256 = IMPORTER.digest(stale.main.indices_hex.hex_decode())
	check(IMPORTER.patched_mesh(baseline, stale) == null, "Reject out-of-range candidate even with matching checksum")
	stale = manifest.duplicate(true)
	stale.lod_edge = 0.001
	check(IMPORTER.patched_mesh(baseline, stale) == null, "Reject understated error")
	scene.free()
	finish()

func finish() -> void:
	print("FOLIAGE_LOD_IMPORT failures=", failures.size())
	quit(0 if failures.is_empty() else 1)
