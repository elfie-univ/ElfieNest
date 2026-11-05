extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var model_path := "res://rooms/estate/ElfieNest-complete-final.glb"
	var imported := ConfigFile.new()
	assert(imported.load(model_path + ".import") == OK)
	var cached: String = imported.get_value("remap", "path")
	var receipt := FileAccess.get_file_as_string(cached.get_basename() + ".md5")
	if not receipt.contains(FileAccess.get_md5(model_path)):
		push_error("The imported Godot model does not match the edited formal GLB")
		quit(1)
		return
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var ribbon := estate.find_child("WholeLakeRibbon", true, false) as MeshInstance3D
	var points: PackedVector3Array = ribbon.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var grounds: Array[MeshInstance3D] = []
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.visible and (mesh.has_meta("source_ground") or preload("res://rooms/estate/estate_bank_cleanup.gd").is_bank(mesh)):
			if str(mesh.get_meta("source_ground", "")) == "CY SHORE solid Continuous lawn with true lake opening" and int(mesh.get_meta("source_surface", -1)) == 0:
				if not mesh.mesh.surface_get_format(0) & Mesh.ARRAY_FORMAT_TEX_UV2:
					push_error("The repaired meadow patch lost its authored secondary UVs: " + str(mesh.name))
					quit(1)
					return
			grounds.append(mesh)
	for ground: MeshInstance3D in grounds:
		var faces := ground.mesh.get_faces()
		for i in range(0, faces.size(), 3):
			var triangle := PackedVector3Array([ground.global_transform * faces[i], ground.global_transform * faces[i + 1], ground.global_transform * faces[i + 2]])
			for sample: Vector3 in [triangle[0], triangle[1], triangle[2], (triangle[0] + triangle[1] + triangle[2]) / 3.0]:
				if sample.y <= -0.389 or sample.x > 28.0 or sample.x < 23.0 or sample.z < 25.5 or sample.z > 32.0: continue
				if sample.y > -0.389 and sample.y < 0.4399 and sample.x > 24.6001 and sample.x < 26.9999 and sample.z > 27.5937 and sample.z < 30.1534:
					push_error("Soil remains inside the complete stone shoulder width: %s at %s" % [ground.name, sample])
					quit(1)
					return
				for group in range(points.size() / 4 - 1):
					var a := points[group * 4]
					var b := points[(group + 1) * 4]
					if minf(a.distance_to(points[0]), a.distance_to(points[-4])) > 1.6: continue
					if sample.z <= minf(a.z, b.z) + 0.0001 or sample.z >= maxf(a.z, b.z) - 0.0001: continue
					var boundary := lerpf(a.x, b.x, (sample.z - a.z) / (b.z - a.z))
					if sample.x > boundary + 0.003:
						push_error("Exposed soil projects beyond the land-side edge of the junction light: %s at %s" % [ground.name, sample])
						quit(1)
						return
	for endpoint: int in [0, points.size() - 4]:
		var end := points[endpoint + 1]
		for group in range(points.size() / 4):
			var at := group * 4
			if points[at + 1].distance_to(end) > 1.4: continue
			for row in range(3):
				var sample := (points[at + row] + points[at + row + 1]) * 0.5
				for ground: MeshInstance3D in grounds:
					var box := ground.global_transform * ground.get_aabb()
					if not box.grow(0.3).has_point(sample): continue
					var faces := ground.mesh.get_faces()
					for i in range(0, faces.size(), 3):
						var hit: Variant = Geometry3D.segment_intersects_triangle(sample + Vector3(0.22, 0, 0), sample + Vector3(0.004, 0, 0), ground.global_transform * faces[i], ground.global_transform * faces[i + 1], ground.global_transform * faces[i + 2])
						if hit is Vector3:
							push_error("Soil obscures the exposed shore light at the waterfall: %s at %s" % [ground.name, sample])
							quit(1)
							return
		var wall_name := "north" if end.z < 29.0 else "south"
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % wall_name, true, false) as MeshInstance3D
		var box := wall.global_transform * wall.get_aabb()
		var plane := box.position.z if wall_name == "north" else box.end.z
		for row in range(4):
			assert(absf(points[endpoint + row].z - plane) < 0.002, "The entire sloping light profile must terminate at the wall plane")
	var wall_boxes: Array[AABB] = []
	for side in ["north", "south"]:
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side, true, false) as MeshInstance3D
		wall_boxes.append(wall.global_transform * wall.get_aabb())
	for batch: MultiMeshInstance3D in estate.find_children("*", "MultiMeshInstance3D", true, false):
		var local := batch.multimesh.mesh.get_aabb()
		if local.size.y > 3.0 or local.size.x > 4.0 or local.size.z > 4.0: continue
		var batch_box := batch.global_transform * batch.get_aabb()
		if batch_box.position.x > 28.0 or batch_box.end.x < 23.0 or batch_box.position.z > 32.0 or batch_box.end.z < 25.0: continue
		var group_id := str(batch.get_meta("source_group", "")).trim_prefix("__ELFIE_INST_GROUP_").to_int()
		for i in range(batch.multimesh.instance_count):
			var pose := batch.global_transform * batch.multimesh.get_instance_transform(i)
			var box := pose * local
			if box.position.y > 2.0 or box.position.x > 28.0 or box.end.x < 23.0: continue
			var flower_group := group_id >= 91 and group_id <= 94 or group_id >= 98 and group_id <= 101
			var flower_strip := flower_group and pose.origin.x > 20.0 and pose.origin.x < 26.0 and (pose.origin.z >= 25.85 and pose.origin.z <= 27.25 or pose.origin.z >= 30.5 and pose.origin.z <= 31.8)
			if flower_strip:
				for wall_box in wall_boxes:
					if box.intersects(wall_box):
						push_error("A flower intersects the waterfall side wall: %s" % batch.name)
						quit(1)
						return
			for group in range(points.size() / 4 - 1):
				var a := points[group * 4]
				var b := points[(group + 1) * 4]
				if minf(a.distance_to(points[0]), a.distance_to(points[-4])) > (2.6 if flower_strip else 1.6): continue
				# Use bounds for the broad phase and actual plant vertices for the
				# sloping shore: a rotated AABB alone produces false intersections.
				if box.end.z < minf(a.z, b.z) - 0.02 or box.position.z > maxf(a.z, b.z) + 0.02: continue
				if box.end.x > minf(a.x, b.x) - 0.04 and box.position.x < 28.0:
					if absf(b.z - a.z) < 0.000001: continue
					for surface in range(batch.multimesh.mesh.get_surface_count()):
						var vertices: PackedVector3Array = batch.multimesh.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
						for vertex in vertices:
							var point: Vector3 = pose * vertex
							if point.z < minf(a.z, b.z) or point.z > maxf(a.z, b.z): continue
							var edge_x := lerpf(a.x, b.x, (point.z - a.z) / (b.z - a.z))
							if point.x > edge_x - 0.025:
								push_error("An instanced plant protrudes into the cleaned light/wall junction: %s" % batch.name)
								quit(1)
								return
	print("PASS: both exposed sloping shore lights meet the complete vertical stone faces without soil intrusion")
	estate.free()
	quit(0)
