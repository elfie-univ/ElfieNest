extends Node3D
## Computed review geometry, not production collisions or a navigation bake.
const HEIGHT := 2.0
const JOIN_MARGIN := 0.05
const CELL := 4.0
var report: Dictionary = {}
var _ground: Dictionary = {}
var edge_samples := 0
var beds: Node3D

func bed_contains(point: Vector2) -> bool:
	return beds != null and bool(beds.call("contains_point",point))

func build(estate: Node3D) -> void:
	var terrain := estate.find_child("GardenCollision_Terrain", true, false)
	var ground_faces := PackedVector3Array()
	for shape: CollisionShape3D in terrain.find_children("*", "CollisionShape3D", true, false):
		for p: Vector3 in (shape.shape as ConcavePolygonShape3D).get_faces():
			ground_faces.append(shape.global_transform * p)
	index_ground(ground_faces)
	print("PLANT_ZONES_GROUND_READY cells=",_ground.size())
	beds = load("res://runtime/lab/estate_plant_beds.gd").new()
	add_child(beds)
	beds.call("build",estate,Callable(self,"ground_height"),Callable(self,"merge_footprints"))
	var categories: Dictionary = {"groundcover": [], "shrubs": [], "planting": []}
	var instances := 0
	var bed_covered := 0
	var root_points: Dictionary = {}
	var woodland_roots := {"groundcover":{},"shrubs":{},"planting":{}}
	var woodland_parts := 0
	# Read the same authored world matrices used by the renderer. MultiMesh
	# readback can return identity transforms on a headless rendering backend.
	var file := FileAccess.open(CompleteEstateFinal.INSTANCE_SIDECAR_PATH, FileAccess.READ)
	if file == null:
		push_error("Plant review cannot read the authored instance matrices")
		return
	var magic := file.get_buffer(8).get_string_from_ascii()
	var version := file.get_32()
	var group_count := file.get_32()
	file.get_32()
	if magic != CompleteEstateFinal.SIDECAR_MAGIC or version != 1:
		push_error("Invalid authored instance header")
		return
	var source_extent := Rect2()
	var first := true
	for _group in range(group_count):
		var name_length := file.get_32()
		var count := file.get_32()
		var group := file.get_buffer(name_length).get_string_from_utf8()
		var matrices := file.get_buffer(count*64).to_float32_array()
		var number := group.trim_prefix("__ELFIE_INST_GROUP_").to_int()
		# These are the landscape planting families of this fixed source asset;
		# groups 0–51 are trees and 82–87 are stones, never treated as flowers.
		if not ((number >= 52 and number <= 81) or (number >= 88 and number <= 132)):
			continue
		var category := "planting"
		if number in [52,53,54,88,89,90,104,105,106,107,108,109,123,124,125,126,127,128]:
			category = "groundcover"
		elif number in [55,56,102,103,110,111]:
			category = "shrubs"
		var marker := estate.find_child(group, true, false) as MeshInstance3D
		if marker == null:
			push_error("Missing authored planting template " + group)
			continue
		for surface in range(marker.mesh.get_surface_count()):
			var material := marker.mesh.surface_get_material(surface)
			var label := material.resource_name.to_lower() if material != null else ""
			if label.begins_with("layered low groundcover"):
				category = "groundcover"
			elif label.begins_with("mixed low shrub"):
				category = "shrubs"
		var bounds := marker.mesh.get_aabb()
		var woodland := bool((marker.get_meta("extras",{}) as Dictionary).get("woodlandUnderstory",false))
		for index in range(count):
			var offset := index*16
			var frame := estate.global_transform * Transform3D(Basis(Vector3(matrices[offset],matrices[offset+1],matrices[offset+2]),Vector3(matrices[offset+4],matrices[offset+5],matrices[offset+6]),Vector3(matrices[offset+8],matrices[offset+9],matrices[offset+10])),Vector3(matrices[offset+12],matrices[offset+13],matrices[offset+14]))
			var origin := Vector2(frame.origin.x, frame.origin.z)
			if first:
				source_extent = Rect2(origin,Vector2.ZERO)
				first = false
			source_extent = source_extent.expand(origin)
			instances += 1
			var root_key := str(Vector3i(roundi(frame.origin.x*1000),roundi(frame.origin.y*1000),roundi(frame.origin.z*1000)))
			if woodland:
				woodland_roots[category][root_key] = true
				woodland_parts += 1
			if bool(beds.call("walkable_contains",origin)):
				continue
			if bed_contains(origin):
				bed_covered += 1
				continue
			var points := PackedVector2Array()
			for corner in range(8):
				var local := bounds.position + Vector3(bounds.size.x if corner & 1 else 0.0, bounds.size.y if corner & 2 else 0.0, bounds.size.z if corner & 4 else 0.0)
				var point := frame * local
				points.append(Vector2(point.x, point.z))
			var key := category+"/"+root_key
			if not root_points.has(key):
				root_points[key] = {"category":category,"points":PackedVector2Array()}
			var cloud: PackedVector2Array = root_points[key]["points"]
			cloud.append_array(points)
			root_points[key]["points"] = cloud
	file.close()
	for root: Dictionary in root_points.values():
		var hull := Geometry2D.convex_hull(root["points"])
		if hull.size() > 3 and hull[0].is_equal_approx(hull[-1]):
			hull.resize(hull.size()-1)
		if hull.size() < 3:
			continue
		for polygon: PackedVector2Array in Geometry2D.offset_polygon(hull,JOIN_MARGIN):
			categories[root["category"]].append(polygon)
	print("PLANT_ZONES_FOOTPRINTS_READY instances=",instances)
	var colors := {"groundcover": Color(0.95,0.18,0.2,0.65), "shrubs": Color(0.65,0.22,1.0,0.7), "planting": Color(1.0,0.38,0.12,0.65)}
	var regions := 0
	for category: String in categories:
		print("PLANT_ZONES_MERGE_START ",category)
		var merged := merge_in_patches(categories[category])
		print("PLANT_ZONES_MERGE_DONE ",category," regions=",merged.size())
		regions += merged.size()
		_add_volumes(category, merged, colors[category])
		report[category] = {"input_pieces": categories[category].size(), "regions": merged.size()}
	# Tree trunks remain the exact already-authored trunk geometry, separate from
	# the two-metre plant protection display. No canopy is made into an obstacle.
	var trunks := estate.find_child("GardenCollision_TreeTrunks", true, false)
	var trunk_shapes := 0
	for shape: CollisionShape3D in trunks.find_children("*", "CollisionShape3D", true, false):
		var visual := MeshInstance3D.new()
		visual.mesh = shape.shape.get_debug_mesh()
		visual.material_override = _material(Color(1.0,0.8,0.15,0.9))
		add_child(visual)
		visual.global_transform = shape.global_transform
		trunk_shapes += 1
	var woodland_counts := {}
	for category: String in woodland_roots:
		woodland_counts[category] = woodland_roots[category].size()
	report.merge({"source_instances": instances, "source_extent": str(source_extent), "merged_regions": regions, "continuous_beds": beds.get("report"), "bed_covered_instances":bed_covered, "woodland_roots":woodland_counts, "woodland_parts":woodland_parts, "height_m": HEIGHT, "join_margin_m": JOIN_MARGIN, "terrain_edge_samples": edge_samples, "tree_shape_groups": trunk_shapes, "production_collisions_modified": false, "navigation_baked": false})
	print("ESTATE_PLANT_ZONES " + JSON.stringify(report))

func merge_in_patches(input: Array) -> Array[PackedVector2Array]:
	# Computational partition only: retain each whole authored footprint. Pieces
	# may overlap across partition edges, so no plant coverage or passage changes.
	var patches: Dictionary = {}
	for polygon: PackedVector2Array in input:
		var center := _bounds(polygon).get_center()
		var key := Vector2i(floori(center.x/4.0),floori(center.y/4.0))
		if not patches.has(key):
			patches[key] = []
		patches[key].append(polygon)
	var result: Array[PackedVector2Array] = []
	for key: Vector2i in patches:
		result.append_array(merge_footprints(patches[key]))
	# Merge the much smaller result again across patch boundaries. Preserve
	# hole-producing overlaps rather than closing genuine unoccupied ground.
	return merge_footprints(result)

func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material

func _bounds(polygon: PackedVector2Array) -> Rect2:
	var bounds := Rect2(polygon[0],Vector2.ZERO)
	for p in polygon:
		bounds = bounds.expand(p)
	return bounds.grow(0.0001)

func _cells(bounds: Rect2) -> Array[Vector2i]:
	var cells: Array[Vector2i] = []
	for x in range(floori(bounds.position.x/CELL),floori(bounds.end.x/CELL)+1):
		for y in range(floori(bounds.position.y/CELL),floori(bounds.end.y/CELL)+1):
			cells.append(Vector2i(x,y))
	return cells

func merge_footprints(input: Array) -> Array[PackedVector2Array]:
	var active: Dictionary = {}
	var buckets: Dictionary = {}
	var next_id := 0
	for source: PackedVector2Array in input:
		var polygon := source
		var changed := true
		while changed:
			changed = false
			var bounds := _bounds(polygon)
			var candidates := {}
			for cell in _cells(bounds):
				for id: int in buckets.get(cell, []):
					if active.has(id):
						candidates[id] = true
			for id: int in candidates:
				var other: PackedVector2Array = active[id]
				if not bounds.intersects(_bounds(other)):
					continue
				var union := Geometry2D.merge_polygons(polygon, other)
				# If a union produces holes, keep its overlapping inputs instead of
				# capping the hole and falsely filling a real clear passage.
				if union.size() == 1:
					polygon = union[0]
					active.erase(id)
					changed = true
					break
		active[next_id] = polygon
		for cell in _cells(_bounds(polygon)):
			if not buckets.has(cell):
				buckets[cell] = []
			buckets[cell].append(next_id)
		next_id += 1
	var result: Array[PackedVector2Array] = []
	for polygon: PackedVector2Array in active.values():
		result.append(polygon)
	return result

func index_ground(faces: PackedVector3Array) -> void:
	_ground.clear()
	for i in range(0,faces.size(),3):
		var a := Vector2(faces[i].x,faces[i].z)
		var b := Vector2(faces[i+1].x,faces[i+1].z)
		var c := Vector2(faces[i+2].x,faces[i+2].z)
		if absf((b-a).cross(c-a)) < 0.000001:
			continue
		for cell in _cells(_bounds(PackedVector2Array([a,b,c]))):
			if not _ground.has(cell):
				_ground[cell] = []
			_ground[cell].append([faces[i],faces[i+1],faces[i+2]])

func ground_height(point: Vector2) -> float:
	var cell := Vector2i(floori(point.x/CELL),floori(point.y/CELL))
	var found := -INF
	var closest := INF
	var closest_height := 0.0
	for triangle: Array in _ground.get(cell, []):
		var a: Vector3 = triangle[0]
		var b: Vector3 = triangle[1]
		var c: Vector3 = triangle[2]
		var aa := Vector2(a.x,a.z)
		var bb := Vector2(b.x,b.z)
		var cc := Vector2(c.x,c.z)
		var denominator := (bb-aa).cross(cc-aa)
		var u := (point-aa).cross(cc-aa)/denominator
		var v := (bb-aa).cross(point-aa)/denominator
		if u >= -0.0001 and v >= -0.0001 and u+v <= 1.0001:
			found = maxf(found,a.y+u*(b.y-a.y)+v*(c.y-a.y))
		for edge in [[a,b],[b,c],[c,a]]:
			var p: Vector3 = edge[0]
			var q: Vector3 = edge[1]
			var pp := Vector2(p.x,p.z)
			var delta := Vector2(q.x,q.z)-pp
			var t := clampf((point-pp).dot(delta)/maxf(delta.length_squared(),0.000001),0,1)
			var distance := point.distance_squared_to(pp+delta*t)
			if distance < closest:
				closest = distance
				closest_height = lerpf(p.y,q.y,t)
	if is_finite(found):
		return found
	edge_samples += 1
	return closest_height

func _add_volumes(label: String, polygons: Array[PackedVector2Array], color: Color) -> void:
	var vertices := PackedVector3Array()
	for polygon in polygons:
		var bottom := PackedVector3Array()
		for p in polygon:
			bottom.append(Vector3(p.x,ground_height(p)+0.015,p.y))
		var indices := Geometry2D.triangulate_polygon(polygon)
		for index: int in indices:
			vertices.append(bottom[index]+Vector3.UP*HEIGHT)
		for i in range(bottom.size()):
			var a := bottom[i]
			var b := bottom[(i+1)%bottom.size()]
			vertices.append_array(PackedVector3Array([a,b,b+Vector3.UP*HEIGHT,a,b+Vector3.UP*HEIGHT,a+Vector3.UP*HEIGHT]))
	if vertices.is_empty():
		return
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.mesh = mesh
	visual.material_override = _material(color)
	add_child(visual)
