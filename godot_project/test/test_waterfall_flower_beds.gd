extends SceneTree
## Measure the approved shared flower prototypes in the saved waterside SCN.
const SUPPORT := preload("res://test/split_estate_test_support.gd")
const FAMILIES := {"057": ["part_00005", "part_00006", "part_00007", "part_00008"], "064": ["part_00012", "part_00013", "part_00014", "part_00015"]}
var failures: Array[String] = []
var reaches := {}

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var scene := load("res://nest/courtyard/areas/waterside/waterside-layout.scn").instantiate() as Node3D
	root.add_child(scene)
	var plant_library := load("res://nest/courtyard/parts/shared/plant-library.glb") as PackedScene
	var positions := {}
	for family: String in FAMILIES:
		for source: String in FAMILIES[family]:
			positions[source] = {}
			reaches[source] = {}
	for batch: MultiMeshInstance3D in scene.find_children("*", "MultiMeshInstance3D", true, false):
		var placement := batch.get_parent()
		if not SUPPORT.is_placement(placement): continue
		if placement.library.resource_path != plant_library.resource_path: continue
		var source := str(placement.source_nodes[batch.get_index()])
		if not positions.has(source): continue
		var extras: Dictionary = batch.multimesh.mesh.get_meta("nest_source_extras", {})
		if not str(extras.get("source_name", "")).begins_with("__ELFIE_INST_GROUP_"):
			failures.append("Flower component lost its canonical provenance: " + source)
		var data: Dictionary = SUPPORT.canonical_batch(batch)
		var ids: PackedInt32Array = batch.get_meta("source_instance_indices", PackedInt32Array())
		var group := str(batch.get_meta("source_group", ""))
		var component := 0
		for family: String in FAMILIES:
			if source in FAMILIES[family]: component = FAMILIES[family].find(source)
		var has_ids: bool = ids.size() == data.instance_count and group.begins_with("__ELFIE_INST_GROUP_")
		var root_group: int = int(group.trim_prefix("__ELFIE_INST_GROUP_"))-component if has_ids else -1
		for index: int in data.instance_count:
			var frame: Transform3D = batch.global_transform * SUPPORT.instance_transform(batch, index)
			var point := frame.origin
			var key: String = "source:%d/root:%d" % [root_group, ids[index]] if has_ids else "origin:%.4f/%.4f/%.4f" % [point.x, point.y, point.z]
			if positions[source].has(key): failures.append("Duplicate canonical flower root/component ID: %s %s" % [source, key])
			positions[source][key] = point
			var bounds: AABB = frame * batch.multimesh.mesh.get_aabb()
			reaches[source][key] = Vector2(bounds.size.x, bounds.size.z).length() * 0.5
	check_shoulders(positions)
	check_lakeside_strip(positions)
	for failure: String in failures: push_error(failure)
	print("WATERFALL_FLOWER_BEDS failures=", failures.size())
	scene.free()
	quit(0 if failures.is_empty() else 1)

func selected(positions: Dictionary, source: String, side: String, strip: bool) -> Dictionary:
	var result := {}
	for key: String in positions[source]:
		var point: Vector3 = positions[source][key]
		if strip:
			var line := [Vector2(25.85,24.58),Vector2(26.25,24.575),Vector2(26.75,24.648),Vector2(27.25,24.776)] if side == "north" else [Vector2(30.5,24.784),Vector2(31,24.534),Vector2(31.5,24.218),Vector2(32,23.887)]
			for index: int in range(line.size() - 1):
				if point.z < line[index].x or point.z > line[index + 1].x: continue
				var edge := lerpf(line[index].y, line[index + 1].y, inverse_lerp(line[index].x, line[index + 1].x, point.z))
				if edge - point.x >= 0.18 and edge - point.x <= 0.60: result[key] = point
		else:
			var low := 26.7 if side == "north" else 30.5
			var high := 27.2 if side == "north" else 31.0
			if point.x > 23.55 and point.x < 24.3 and point.z > low and point.z < high: result[key] = point
	return result

func check_components(positions: Dictionary, family: String, side: String, strip: bool) -> Dictionary:
	var reference := selected(positions, FAMILIES[family][0], side, strip)
	# Repacking/pruning assigns different source indices to each component.
	# Match complete plants one-to-one by actual saved world roots instead.
	for source: String in FAMILIES[family]:
		var used := {}
		for key: String in reference:
			var root: Vector3 = reference[key]
			var nearest_id := ""
			var distance := INF
			for candidate: String in positions[source]:
				if used.has(candidate): continue
				var point: Vector3 = positions[source][candidate]
				if root.distance_to(point) < distance:
					distance = root.distance_to(point)
					nearest_id = candidate
			# Wall-side components may be moved/tilted independently. Require
			# one-to-one membership within the real plant envelopes, not identical
			# pivots or cross-component indices after pruning/repacking.
			var envelope: float = reaches[FAMILIES[family][0]][key] + float(reaches[source].get(nearest_id, 0.0))
			if distance <= envelope + 0.0001:
				used[nearest_id] = true
				if distance > 0.0001: print("FLOWER_COMPONENT_ENVELOPES root=", root, " component=", source, " distance=", distance, " combined_reach=", envelope)
			else:
				print("FLOWER_MISSING_ROOT family=", family, " side=", side, " strip=", strip, " root=", root, " component=", source, " nearest_distance=", distance)
				failures.append("Flower root lost a component: family=%s side=%s strip=%s component=%s" % [family, side, strip, source])
	return reference

func check_shoulders(positions: Dictionary) -> void:
	for side: String in ["north", "south"]:
		for family: String in FAMILIES:
			var points := check_components(positions, family, side, false)
			var outer := false
			for point: Vector3 in points.values(): outer = outer or point.x >= 24.0
			if points.size() < 2 or not outer: failures.append("Flower shoulder coverage missing: family=%s side=%s count=%d outer=%s" % [family, side, points.size(), outer])
			print("FLOWER_SHOULDER family=", family, " side=", side, " count=", points.size(), " outer=", outer)

func check_lakeside_strip(positions: Dictionary) -> void:
	for side: String in ["north", "south"]:
		var total := 0
		var low := INF
		var high := -INF
		for family: String in FAMILIES:
			var points := check_components(positions, family, side, true)
			if points.size() < 4: failures.append("Lakeside strip lacks a complete flower family: family=%s side=%s count=%d" % [family, side, points.size()])
			total += points.size()
			for point: Vector3 in points.values():
				low = minf(low, point.z)
				high = maxf(high, point.z)
		if total < 12 or high - low < 1.0: failures.append("Lakeside strip coverage missing: side=%s total=%d span=%f" % [side, total, high - low])
		print("FLOWER_LAKESIDE_STRIP side=", side, " total=", total, " span=", high - low)
