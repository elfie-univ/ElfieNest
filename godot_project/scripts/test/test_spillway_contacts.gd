extends SceneTree

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var display := preload("res://rooms/estate/estate_water_display.gd").new()
	root.add_child(display)
	display.bind(estate,Environment.new(),false)
	var rim := estate.find_child("FountainConcealedRim",true,false) as MeshInstance3D
	var rim_points: PackedVector3Array = rim.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for side in ["north","south"]:
		var strip := display.get_node("SpillwayEdge_" + side) as MeshInstance3D
		var route: PackedVector3Array = strip.get_meta("light_route")
		var edge: PackedVector3Array = strip.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var join := PackedVector3Array([rim_points[-2],rim_points[-1]]) if side == "north" else PackedVector3Array([rim_points[0],rim_points[1]])
		for point: Vector3 in join:
			var world := rim.global_transform * point
			if minf(world.distance_to(edge[0]),world.distance_to(edge[1])) > 0.0002:
				push_error("Fountain/channel lamp corner must share the full cut edge, not just its centre")
				quit(1)
				return
		if route.size() < 2 or edge.size() != route.size() * 2:
			push_error("Channel lamps must form a continuous ribbon along the upper edge")
			quit(1)
			return
		for point: Vector3 in route:
			if absf(point.y - route[0].y) > 0.10:
				push_error("Channel lamps must remain on the upper edge, without descending along the waterfall")
				quit(1)
				return
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side,true,false) as MeshInstance3D
		var curtain := estate.find_child("Continuous shallow waterfall from solid spillway crest",true,false) as MeshInstance3D
		var crest := (curtain.global_transform * curtain.get_aabb()).position.x
		if absf(route[-1].x - crest) > 0.015 or strip.layers != rim.layers:
			push_error("Both lamps must reach the real upper-edge end and use the fountain rim lighting layer")
			quit(1)
			return
		for point: Vector3 in route:
			if point.x < (wall.global_transform * wall.get_aabb()).position.x + 0.08: continue
			var height := _wall_top_at(wall, point.x, point.z)
			if is_inf(height) or point.y - height < 0.004 or point.y - height > 0.015:
				push_error("The lamp must follow the real stone top without floating or clipping into it")
				quit(1)
				return
		var material := strip.get_active_material(0) as BaseMaterial3D
		var rim_material := rim.get_active_material(0) as BaseMaterial3D
		if material.albedo_color != rim_material.albedo_color or not is_equal_approx(material.roughness,rim_material.roughness):
			push_error("Channel lamps must retain the actual fountain rim appearance")
			quit(1)
			return
	var shore := estate.find_child("WholeLakeRibbon",true,false) as MeshInstance3D
	var shore_vertices: PackedVector3Array = shore.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for side in ["north","south"]:
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side,true,false) as MeshInstance3D
		var stone := wall.global_transform * wall.get_aabb()
		for point: Vector3 in shore_vertices:
			if point.x > stone.position.x and point.x < stone.end.x and point.z > stone.position.z and point.z < stone.end.z:
				push_error("Shore lamp must stop outside the waterfall stone shoulders instead of flashing through their faces")
				quit(1)
				return
	for night in [true,false]:
		display.sample(1.0,night)
		for side in ["north","south"]:
			var material := (display.get_node("SpillwayEdge_" + side) as MeshInstance3D).get_active_material(0) as BaseMaterial3D
			if not material.emission_enabled or (material.emission_energy_multiplier > 0.0) != night:
				push_error("Horizontal channel lamps must retain day/night switching")
				quit(1)
				return
	var splash := display.get_node("WaterfallLandingSplash") as CPUParticles3D
	if not splash.emitting or splash.mesh == null:
		push_error("Waterfall landing droplets must remain visible")
		quit(1)
		return
	print("PASS: two horizontal channel lamps join the fountain rim, stop before the slopes and retain day/night switching")
	estate.free()
	display.free()
	quit(0)

func _wall_top_at(wall: MeshInstance3D, x: float, z: float) -> float:
	var faces := wall.mesh.get_faces()
	var top := -INF
	for index in range(0, faces.size(), 3):
		var hit: Variant = Geometry3D.segment_intersects_triangle(Vector3(x,2.0,z), Vector3(x,-2.0,z), wall.global_transform*faces[index], wall.global_transform*faces[index+1], wall.global_transform*faces[index+2])
		if hit is Vector3: top = maxf(top, (hit as Vector3).y)
	return top
