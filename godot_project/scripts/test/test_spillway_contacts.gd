extends SceneTree

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var display := preload("res://rooms/estate/estate_water_display.gd").new()
	root.add_child(display)
	display.bind(estate,Environment.new(),false)
	var backing := estate.find_child("CY R001 spillway supporting outlet face",true,false) as MeshInstance3D
	var backing_box := backing.global_transform * backing.get_aabb()
	if backing_box.end.x > 24.881 or backing_box.position.y > -0.649:
		push_error("Imported backing must descend vertically underground, clear of the landing")
		quit(1)
		return
	var stone_front := -INF
	for y: float in [0.35,0.0,-0.35,-0.6]:
		var hits := PackedFloat32Array()
		var faces := backing.mesh.get_faces()
		for i in range(0,faces.size(),3):
			var hit: Variant = Geometry3D.segment_intersects_triangle(Vector3(26.0,y,28.87),Vector3(24.0,y,28.87),backing.global_transform*faces[i],backing.global_transform*faces[i+1],backing.global_transform*faces[i+2])
			if hit is Vector3: hits.append((hit as Vector3).x)
		hits.sort()
		if hits.is_empty() or (not is_inf(stone_front) and absf(hits[-1]-stone_front)>0.0001):
			push_error("Backing front must have one constant horizontal position at every height")
			quit(1)
			return
		stone_front = hits[-1]
	var channel := estate.find_child("COMPLETE Short east spillway",true,false) as MeshInstance3D
	var water := channel.get_active_material(0) as ShaderMaterial
	if float(water.get_shader_parameter("water_opacity")) < 0.70:
		push_error("The shallow channel must retain a visible translucent water layer")
		quit(1)
		return
	var tint: Vector3 = water.get_shader_parameter("water_tint")
	if tint.x < 0.4 or tint.z < 0.75 or tint.z <= tint.x:
		push_error("The channel must use pale blue water rather than dark green")
		quit(1)
		return
	var lake := estate.find_child("COMPLETE Inset natural lake",true,false) as MeshInstance3D
	var lake_height := (lake.global_transform * lake.get_aabb()).end.y
	var clearance := [AABB(Vector3(24.7801,-0.3899,27.3937),Vector3(0.7198,1.0,2.9598))]
	for side: String in ["north","south"]:
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side,true,false) as MeshInstance3D
		var stone := wall.global_transform * wall.get_aabb()
		var minimum := Vector3(stone.end.x-0.279,lake_height+0.001,stone.position.z+0.001)
		var maximum := Vector3(stone.end.x-0.001,0.41,stone.end.z-0.001)
		clearance.append(AABB(minimum,maximum-minimum))
	var earth_patches := 0
	for patch: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		if str(patch.get_meta("source_ground","")) != "CY SHORE solid Continuous lawn with true lake opening" or int(patch.get_meta("source_surface",-1)) not in [1,2]:
			continue
		earth_patches += 1
		var box := patch.global_transform * patch.get_aabb()
		if not clearance.any(func(region: AABB) -> bool: return box.intersects(region)): continue
		var faces := patch.mesh.get_faces()
		for index in range(0,faces.size(),3):
			var triangle := PackedVector3Array([patch.global_transform*faces[index],patch.global_transform*faces[index+1],patch.global_transform*faces[index+2]])
			for region: AABB in clearance:
				if _earth_in_bounds(triangle,region):
					push_error("A displayed grass or earth patch still projects into the waterfall or stone shoulder: %s" % patch.name)
					quit(1)
					return
	if earth_patches == 0:
		push_error("The actual displayed earth patches must be checked")
		quit(1)
		return
	var rim := estate.find_child("FountainConcealedRim",true,false) as MeshInstance3D
	var rim_points: PackedVector3Array = rim.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for side in ["north","south"]:
		var strip := display.get_node("SpillwayEdge_" + side) as MeshInstance3D
		var route: PackedVector3Array = strip.get_meta("light_route")
		var edge: PackedVector3Array = strip.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var triangles: PackedInt32Array = strip.mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX]
		for index in range(0,triangles.size(),3):
			var a := edge[triangles[index]]
			var b := edge[triangles[index+1]]
			var c := edge[triangles[index+2]]
			if (b-a).cross(c-a).y <= 0.0:
				push_error("The rounded tip must retain the ribbon's upward face orientation")
				quit(1)
				return
		var join := PackedVector3Array([rim_points[-2],rim_points[-1]]) if side == "north" else PackedVector3Array([rim_points[0],rim_points[1]])
		for point: Vector3 in join:
			var world := rim.global_transform * point
			if minf(world.distance_to(edge[0]),world.distance_to(edge[1])) > 0.0002:
				push_error("Fountain/channel lamp corner must share the full cut edge, not just its centre")
				quit(1)
				return
		if route.size() < 2 or edge.size() != route.size() * 2:
			push_error("Channel lamps must form a continuous ribbon with a shared vertical corner")
			quit(1)
			return
		for point: Vector3 in route:
			if absf(point.y - route[0].y) > 0.10:
				push_error("Channel lamps must remain on the upper edge, without descending along the waterfall")
				quit(1)
				return
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side,true,false) as MeshInstance3D
		# Checking only the centreline misses a ribbon that slopes through the
		# curved top. Sample the actual rendered triangles across their width.
		var wall_start := (wall.global_transform * wall.get_aabb()).position.x
		for index in range(0,triangles.size(),3):
			var a := edge[triangles[index]]
			var b := edge[triangles[index+1]]
			var c := edge[triangles[index+2]]
			for weights: Vector3 in [Vector3(0.2,0.4,0.4),Vector3(0.4,0.2,0.4),Vector3(0.4,0.4,0.2)]:
				var point := a*weights.x+b*weights.y+c*weights.z
				if point.x < wall_start+0.08: continue
				var stone_top := _wall_top_at(wall,point.x,point.z)
				if not is_inf(stone_top) and point.y < stone_top+0.002:
					push_error("The full width of each channel lamp must remain above the curved stone top: side=%s triangle=%s point=%s stone_top=%s" % [side,index / 3,point,stone_top])
					quit(1)
					return
		var curtain := estate.find_child("Continuous shallow waterfall from solid spillway crest",true,false) as MeshInstance3D
		var crest := (curtain.global_transform * curtain.get_aabb()).position.x
		var tip := -INF
		for point: Vector3 in edge: tip = maxf(tip,point.x)
		var drop := display.get_node("SpillwayDrop_" + side) as MeshInstance3D
		for point: Vector3 in drop.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]: tip = maxf(tip, point.x)
		var stone_tip := (wall.global_transform * wall.get_aabb()).end.x
		if route[-1].x <= crest or tip < stone_tip - 0.003 or tip > stone_tip + 0.012 or strip.layers != rim.layers:
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
	var shore_route: PackedVector3Array = shore.get_meta("shoreline")
	for side in ["north","south"]:
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side,true,false) as MeshInstance3D
		var stone := wall.global_transform * wall.get_aabb()
		var outer_z := stone.position.z if side == "north" else stone.end.z
		var endpoint := shore_route[0] if absf(shore_route[0].z - outer_z) < absf(shore_route[-1].z - outer_z) else shore_route[-1]
		if absf(endpoint.z - outer_z) > 0.002 or endpoint.x <= stone.position.x or endpoint.x >= stone.end.x:
			push_error("The shore lamp must join the actual outer stone face without a black soil gap")
			quit(1)
			return
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


func _earth_in_bounds(polygon: PackedVector3Array, bounds: AABB) -> bool:
	for cut: Array in [[0,bounds.position.x,1.0],[0,bounds.end.x,-1.0],[2,bounds.position.z,1.0],[2,bounds.end.z,-1.0],[1,bounds.position.y,1.0],[1,bounds.end.y,-1.0]]:
		var next := PackedVector3Array()
		for i in range(polygon.size()):
			var a := polygon[i]
			var b := polygon[(i+1)%polygon.size()]
			var da: float = (a[cut[0]]-cut[1])*cut[2]
			var db: float = (b[cut[0]]-cut[1])*cut[2]
			if da >= 0.0: next.append(a)
			if (da < 0.0) != (db < 0.0): next.append(a.lerp(b,da/(da-db)))
		polygon = next
		if polygon.size() < 3: return false
	for i in range(1,polygon.size()-1):
		if (polygon[i]-polygon[0]).cross(polygon[i+1]-polygon[0]).length_squared() > 1e-12: return true
	return false
