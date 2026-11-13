extends RefCounted
## Read saved placement inputs, never renderer/GPU instance readback.
const PLACEMENT := preload("res://nest/assembly/glb_placement.gd")

static func placements(estate: Node) -> Array[Node]:
	var result: Array[Node] = []
	for node: Node in estate.find_children("*", "", true, false):
		if is_placement(node): result.append(node)
	return result

static func is_placement(node: Node) -> bool:
	# A source .gd and mounted PCK .gdc can be distinct Script resources.
	if not node.has_method("bind_meshes") or not node.has_method("import_meshes"): return false
	var properties := {}
	for property: Dictionary in node.get_property_list(): properties[str(property.name)] = true
	for required: String in ["library", "source_nodes", "material_variants", "instance_batches"]:
		if not properties.has(required): return false
	return node.get("library") is PackedScene and node.get("source_nodes") is PackedStringArray and node.get("instance_batches") is Dictionary

static func canonical_batch(batch: MultiMeshInstance3D) -> Dictionary:
	var placement := batch.get_parent()
	if not is_placement(placement): return {}
	var data: Dictionary = placement.instance_batches.get(batch.get_index(), {})
	if data.is_empty() or data.has("buffer"): return data
	var resolved := data.duplicate()
	resolved["buffer"] = placement.instance_buffer(data)
	return resolved

static func instance_transform(batch: MultiMeshInstance3D, index: int) -> Transform3D:
	var data := canonical_batch(batch)
	assert(not data.is_empty() and data.transform_format == MultiMesh.TRANSFORM_3D)
	var stride := 12 + (4 if data.use_colors else 0) + (4 if data.use_custom_data else 0)
	var buffer: PackedFloat32Array = data.buffer
	var offset := index * stride
	return Transform3D(
		Vector3(buffer[offset], buffer[offset + 4], buffer[offset + 8]),
		Vector3(buffer[offset + 1], buffer[offset + 5], buffer[offset + 9]),
		Vector3(buffer[offset + 2], buffer[offset + 6], buffer[offset + 10]),
		Vector3(buffer[offset + 3], buffer[offset + 7], buffer[offset + 11]))

static func batch_error(estate: Node) -> String:
	var batches := 0
	var instances := 0
	var libraries := {}
	var placement_count := 0
	for placement: Node in placements(estate):
		if placement.library == null: return "Placement has no GLB library"
		libraries[placement.library.resource_path] = true
		placement_count += 1
		if placement.source_nodes.size() != placement.get_child_count(): return "Placement/source cardinality changed"
		var meshes: Dictionary = placement.import_meshes(placement.library.resource_path)
		for index: int in placement.get_child_count():
			var node := placement.get_child(index)
			if not node is MultiMeshInstance3D: continue
			var data := canonical_batch(node)
			if data.is_empty(): return "Missing canonical instance batch: " + str(node.get_path())
			var batch: MultiMesh = node.multimesh
			if batch == null or batch.mesh == null: return "Unbound instance batch"
			if data.transform_format != MultiMesh.TRANSFORM_3D: return "Estate batch must retain 3D transforms"
			var stride := 12 + (4 if data.use_colors else 0) + (4 if data.use_custom_data else 0)
			var buffer: PackedFloat32Array = data.buffer
			if buffer.size() != data.instance_count * stride: return "Invalid canonical buffer stride/count"
			if batch.instance_count != data.instance_count or batch.visible_instance_count != data.visible_instance_count or batch.transform_format != data.transform_format or batch.use_colors != data.use_colors or batch.use_custom_data != data.use_custom_data or batch.custom_aabb != data.custom_aabb:
				return "Bound batch configuration differs from canonical input"
			var original: Mesh = PLACEMENT.select_mesh(meshes, placement.source_nodes[index], str(node.get_meta("v044_path", "")), "")
			if original == null or batch.mesh != original: return "Batch lost shared GLB prototype"
			# Shared resource identity preserves authored geometry, materials and LODs.
			for sample: int in data.instance_count:
				if not instance_transform(node, sample).is_finite(): return "Nonfinite canonical instance transform"
			batches += 1
			instances += data.instance_count
	# Count the reachable assembly graph, not all GLBs on disk. Export remaps
	# imported libraries to PackedScene paths; identity does not depend on suffix.
	var expected := {}
	var visited := {}
	collect_libraries(load("res://nest/assembly/estate.tscn") as PackedScene, expected, visited)
	var missing: Array[String] = []
	var unexpected: Array[String] = []
	for path: String in expected:
		if not libraries.has(path): missing.append(path)
	for path: String in libraries:
		if not expected.has(path): unexpected.append(path)
	missing.sort()
	unexpected.sort()
	var observed_batches := 0
	for node: MultiMeshInstance3D in estate.find_children("*", "MultiMeshInstance3D", true, false):
		if is_placement(node.get_parent()):
			observed_batches += 1
			continue
		if node.get_meta("estate_instance_batch", false): continue
		if node.has_meta("nest_instance_owner"):
			var source := node.get_parent().get_parent() as Node3D
			if source.get_instance_id() != node.get_meta("nest_instance_owner") or not is_placement(source.get_parent()):
				return "Missing owner for nested GLB instance batch: " + str(node.get_path())
			var mesh: MultiMesh = node.multimesh
			var input: PackedFloat32Array = mesh.get_meta("nest_instance_buffer", PackedFloat32Array())
			if mesh.mesh == null or mesh.transform_format != MultiMesh.TRANSFORM_3D or input.size() != 12 * mesh.instance_count:
				return "Invalid nested GLB instance batch: " + str(node.get_path())
			continue
		if node.name == &"ReusedFountainDrops" or node.name == &"ArrivalMotes": continue
		return "Unclassified instance batch: " + str(node.get_path())
	var diagnostic := "placements=%d libraries=%d expected_libraries=%d batches=%d observed_batches=%d instances=%d missing=%s unexpected=%s" % [placement_count, libraries.size(), expected.size(), batches, observed_batches, instances, JSON.stringify(missing), JSON.stringify(unexpected)]
	print("SPLIT_CANONICAL ", diagnostic)
	if expected.is_empty() or not missing.is_empty() or not unexpected.is_empty() or batches == 0 or instances == 0:
		return "Split reachable library/canonical instance mismatch: " + diagnostic
	if observed_batches != batches:
		return "Unclassified instance batches: " + diagnostic

	return ""


static func collect_libraries(scene: PackedScene, libraries: Dictionary, visited: Dictionary) -> void:
	if scene == null or visited.has(scene.get_instance_id()): return
	visited[scene.get_instance_id()] = true
	collect_state_libraries(scene.get_state(), libraries, visited)

static func collect_state_libraries(state: SceneState, libraries: Dictionary, visited: Dictionary) -> void:
	if state == null: return
	collect_state_libraries(state.get_base_scene_state(), libraries, visited)
	for index: int in state.get_node_count():
		collect_libraries(state.get_node_instance(index), libraries, visited)
		for property: int in state.get_node_property_count(index):
			var value: Variant = state.get_node_property_value(index, property)
			if not value is PackedScene: continue
			if state.get_node_property_name(index, property) == &"library":
				libraries[value.resource_path] = true
			else:
				collect_libraries(value, libraries, visited)

static func shore_geometry(estate: Node3D) -> RefCounted:
	# Reconstruct measurement inputs from the actual placed lake, without applying
	# the retired loader's destructive bank/foliage preparation a second time.
	var shore := preload("res://nest/courtyard/parts/waterside/estate_shore_finish.gd").new()
	var lake := estate.find_child("COMPLETE Inset natural lake", true, false) as MeshInstance3D
	assert(lake != null and lake.mesh != null)
	var reader := preload("res://nest/spatial/estate_outdoor_access.gd").new()
	var loops: Array[PackedVector2Array] = reader._top_outlines(lake, 0, -1.0)
	reader.free()
	var largest := 0.0
	for polygon: PackedVector2Array in loops:
		var area := 0.0
		for i: int in polygon.size(): area += polygon[i].cross(polygon[(i + 1) % polygon.size()])
		if absf(area) > largest:
			largest = absf(area)
			shore.water = polygon
	assert(not shore.water.is_empty())
	shore.water_bounds = Rect2(shore.water[0], Vector2.ZERO)
	for point: Vector2 in shore.water: shore.water_bounds = shore.water_bounds.expand(point)
	shore.water_height = (lake.global_transform * lake.get_aabb()).end.y
	var first := true
	for part: MeshInstance3D in estate.find_children("Lakeside*", "MeshInstance3D", true, false):
		if not ("bench" in str(part.name) or str(part.name).begins_with("Lakeside back frame")): continue
		var box := part.global_transform * part.get_aabb()
		shore.bench_clearance = box if first else shore.bench_clearance.merge(box)
		first = false
	assert(not first, "Placed lakeside bench is missing")
	shore.bench_clearance = shore.bench_clearance.grow(0.35)
	shore.bench_clearance.position.y = 0.65
	shore.bench_clearance.size.y = 2.0
	return shore
