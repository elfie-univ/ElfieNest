extends SceneTree

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var shore = preload("res://test/split_estate_test_support.gd").shore_geometry(estate)
	var expanded: Array[PackedVector2Array] = Geometry2D.offset_polygon(shore.water, 0.10, Geometry2D.JOIN_ROUND)
	if expanded.size() != 1:
		push_error("Lake border must form one continuous contour")
		quit(1)
		return
	var water_edge := expanded[0]
	for name in ["CY SHORE solid Continuous lawn with true lake opening", "CY R003 corrected CY R002 lakeside gently sloping planted shore", "CY R003 corrected CY R002 lakeside returned solid planting bank", "CY R003 corrected CY SHORE solid Continuous planted lake bank", "CY R003 corrected CY SHORE solid Lake sloping bank", "CY R003 corrected CY R002 continuous natural shore slope 0", "CY R003 corrected CY R002 continuous natural shore slope 1"]:
		var mesh := estate.find_child(name, true, false) as MeshInstance3D
		if mesh == null or not mesh.is_visible_in_tree(): continue
		var faces := mesh.mesh.get_faces()
		for i in range(0, faces.size(), 3):
			var polygon := PackedVector2Array()
			var top := -INF
			for j in range(3):
				var p := mesh.global_transform * faces[i+j]
				top = maxf(top, p.y)
				polygon.append(Vector2(p.x, p.z))
			if top <= shore.water_height + 0.015: continue
			var bounds := Rect2(polygon[0],Vector2.ZERO).expand(polygon[1]).expand(polygon[2])
			if not shore.water_bounds.grow(0.10).intersects(bounds,true): continue
			for overlap: PackedVector2Array in Geometry2D.intersect_polygons(polygon,water_edge):
				var area := 0.0
				for k in range(overlap.size()): area += overlap[k].cross(overlap[(k+1)%overlap.size()])
				if absf(area) > 0.0001:
					push_error("Green land protrudes into the lake: " + name)
					quit(1)
					return
	print("PASS: lake-side lawn and shore do not intrude into the water")
	estate.queue_free()
	quit(0)
