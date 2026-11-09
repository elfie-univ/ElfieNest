extends SceneTree
## The actual land-side edge must be supported around the lake and both waterfall shoulders.

var ground_cells: Dictionary = {}
var ground_faces: Array = []

func _initialize() -> void:
	call_deferred("run")

func _height(point: Vector2) -> float:
	var result := -INF
	for tri: PackedVector3Array in ground_cells.get(Vector2i(floori(point.x), floori(point.y)), []):
		var a := Vector2(tri[0].x, tri[0].z)
		var b := Vector2(tri[1].x, tri[1].z)
		var c := Vector2(tri[2].x, tri[2].z)
		var area := (b - a).cross(c - a)
		if absf(area) < 0.00000001: continue
		var wb := (point - a).cross(c - a) / area
		var wc := (b - a).cross(point - a) / area
		if minf(1.0 - wb - wc, minf(wb, wc)) < -0.00001:
			# ArrayMesh compression moves edge vertices by a few micrometres.
			# Accept physical contact within 0.1 mm, not missing centimetres of land.
			var near := false
			for i in range(3):
				var p := Vector2(tri[i].x,tri[i].z)
				var q := Vector2(tri[(i+1)%3].x,tri[(i+1)%3].z)
				if point.distance_to(Geometry2D.get_closest_point_to_segment(point,p,q)) < 0.0001:near=true
			if not near:continue
		result = maxf(result, tri[0].y * (1.0 - wb - wc) + tri[1].y * wb + tri[2].y * wc)
	return result

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var cleanup := preload("res://nest/estate/estate_bank_cleanup.gd")
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if not mesh.is_visible_in_tree(): continue
		if not (mesh.has_meta("source_ground") or cleanup.is_bank(mesh) or str(mesh.name) in ["GroundPatch_LakeShoreGroundClosure", "GroundPatch_HardscapeSeamClosure"]): continue
		var faces := mesh.mesh.get_faces()
		for i in range(0, faces.size(), 3):
			var tri := PackedVector3Array([mesh.global_transform * faces[i], mesh.global_transform * faces[i + 1], mesh.global_transform * faces[i + 2]])
			var normal := (tri[1] - tri[0]).cross(tri[2] - tri[0])
			if absf(normal.y) < 0.0000001 or maxf(tri[0].y, maxf(tri[1].y, tri[2].y)) > 0.2 or minf(tri[0].y, minf(tri[1].y, tri[2].y)) < -0.2: continue
			var lo := Vector2(minf(tri[0].x, minf(tri[1].x, tri[2].x)), minf(tri[0].z, minf(tri[1].z, tri[2].z)))
			var hi := Vector2(maxf(tri[0].x, maxf(tri[1].x, tri[2].x)), maxf(tri[0].z, maxf(tri[1].z, tri[2].z)))
			if hi.x < 19.0 or lo.x > 44.0 or hi.y < 2.0 or lo.y > 42.0: continue
			ground_faces.append([[tri[0].x,tri[0].y,tri[0].z],[tri[1].x,tri[1].y,tri[1].z],[tri[2].x,tri[2].y,tri[2].z]])
			for x in range(floori(lo.x), floori(hi.x) + 1):
				for z in range(floori(lo.y), floori(hi.y) + 1):
					var key := Vector2i(x, z)
					if not ground_cells.has(key): ground_cells[key] = []
					ground_cells[key].append(tri)
	var ribbon := estate.find_child("WholeLakeRibbon", true, false) as MeshInstance3D
	var vertices: PackedVector3Array = ribbon.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var path: PackedVector3Array = ribbon.get_meta("shoreline")
	var stride := vertices.size() / path.size()
	var edge: Array = []
	var failures: Array = []
	var count := 0
	for i in range(path.size()):
		var p := ribbon.global_transform * vertices[i * stride]
		edge.append([p.x, p.y, p.z])
		if i == path.size() - 1: continue
		var q := ribbon.global_transform * vertices[(i + 1) * stride]
		var steps := maxi(1, ceili(p.distance_to(q) / 0.10))
		for j in range(steps):
			var sample := p.lerp(q, float(j) / steps)
			var height := _height(Vector2(sample.x, sample.z))
			count += 1
			if is_inf(height) or absf(height - sample.y) > 0.006:
				failures.append([sample.x, sample.y, sample.z])
	var walls: Array = []
	var shoulder_failures := 0
	for side in ["north", "south"]:
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side, true, false) as MeshInstance3D
		var box := wall.global_transform * wall.get_aabb()
		var sign := -1.0 if side == "north" else 1.0
		var z := (box.position.z if side == "north" else box.end.z)
		walls.append({"side":side,"min":[box.position.x,box.position.y,box.position.z],"max":[box.end.x,box.end.y,box.end.z]})
		for j in range(1, 41):
			var x := lerpf(box.position.x, box.end.x - 0.11, float(j) / 41)
			if is_inf(_height(Vector2(x, z + sign * 0.006))): shoulder_failures += 1
	var data := {"edge":edge,"ground":ground_faces,"walls":walls,"missing_samples":failures,"samples":count,"shoulder_missing":shoulder_failures}
	var output := FileAccess.open("res://../build/asset_design/lake-ground-closure/measured.json", FileAccess.WRITE)
	output.store_string(JSON.stringify(data))
	output.close()
	print("LAKE_GROUND_CONTACT samples=", count, " missing=", failures.size(), " shoulder_missing=", shoulder_failures)
	estate.free()
	if not failures.is_empty() or shoulder_failures > 0:
		push_error("Actual ground is missing at the land-side shore edge or the waterfall shoulders")
		quit(1)
	else:
		print("PASS: continuous ground contact around the whole shore and both waterfall shoulders")
		quit(0)
