extends SceneTree
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var fixture := Node3D.new()
	root.add_child(fixture)
	var source: Node3D = load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(source)
	var originals: Dictionary = {}
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var label := str(mesh.name)
		if not (label.begins_with("Public stair rail post") or label.begins_with("Central stairwell edge coping") or label.begins_with("Public stair L") or label.begins_with("Working L") or label.begins_with("L1 ") or label.begins_with("L2 ") or label.begins_with("L3 ") or "full stairwell edge" in label): continue
		mesh.reparent(fixture, true)
		originals[mesh] = mesh.mesh
	source.free()
	DAYLIGHT.apply(fixture)
	var glass_count := 0
	for mesh: MeshInstance3D in originals:
		var label := str(mesh.name)
		var final_panel := (label.begins_with("L1 clear glass rail panel") and label.ends_with(" 8")) or ("clear infill" in label and label.ends_with("bay 5"))
		if not final_panel: continue
		glass_count+=1
		var landing := 4.3 if label.begins_with("L1") else (7.1 if "L2" in label else 9.9)
		var local_y := mesh.to_local(fixture.to_global(Vector3(0,landing,0))).y
		for surface in range(mesh.mesh.get_surface_count()):
			var old := (originals[mesh] as Mesh).surface_get_arrays(surface)
			var now := mesh.mesh.surface_get_arrays(surface)
			if not require(old[Mesh.ARRAY_INDEX]==now[Mesh.ARRAY_INDEX],"Glass repair added separate triangles"): return
			var columns: Dictionary={}
			for p: Vector3 in old[Mesh.ARRAY_VERTEX]:
				var key := Vector2(p.x,p.z).snapped(Vector2.ONE*0.00001)
				columns[key]=minf(float(columns.get(key,INF)),p.y)
			for i in range(old[Mesh.ARRAY_VERTEX].size()):
				var p: Vector3=old[Mesh.ARRAY_VERTEX][i]
				var q: Vector3=now[Mesh.ARRAY_VERTEX][i]
				var bottom: float=columns[Vector2(p.x,p.z).snapped(Vector2.ONE*0.00001)]
				var expected := minf(p.y,local_y-0.002) if absf(p.y-bottom)<0.001 else p.y
				if not require(q.is_equal_approx(Vector3(p.x,expected,p.z)),"Glass lower edge leaves a landing gap or upper edge changed: "+label): return
	if not require(glass_count==6,"Missing final glass panel pair on a landing"): return
	var posts := fixture.find_children("LandingTerminalPost*","MeshInstance3D",true,false)
	if not require(posts.size()==2,"Second-floor terminal posts are missing"): return
	for post: MeshInstance3D in posts:
		var bounds := post.transform*post.get_aabb()
		if not require(bounds.position.y<=4.3 and bounds.end.y>=5.10 and bounds.end.y<=5.18,"Terminal post does not connect floor to rail"): return
	var joins: Array[MeshInstance3D]=[]
	joins.assign(posts)
	for mesh: MeshInstance3D in originals:
		if str(mesh.name).begins_with("Public stair rail post"):
			var bounds: AABB=(originals[mesh] as Mesh).get_aabb()
			if bounds.get_center().x<0 and (absf(bounds.end.y-8.0)<0.01 or absf(bounds.end.y-10.8)<0.01): joins.append(mesh)
	if not require(joins.size()==6,"Missing terminal joins"): return
	for post: MeshInstance3D in joins:
		var bounds := post.transform*post.get_aabb()
		if not require(absf(bounds.size.x-0.052)<0.001 and bounds.size.z<=0.053,"Terminal post diameter differs from intermediate supports"): return
		var rail_y := 5.2 if bounds.position.y<5 else (8.0 if bounds.position.y<8 else 10.8)
		if not require(bounds.end.y<rail_y-0.02 and bounds.end.y>rail_y-0.10,"Terminal post intrudes into handrail silhouette"): return
	for mesh: MeshInstance3D in originals:
		if str(mesh.name).begins_with("Public stair L") and "handrail" in str(mesh.name):
			if not require(open_edges(mesh.mesh)==0, "Handrail still has open ends instead of rounded closed end caps: "+str(mesh.name)): return
		var label := str(mesh.name)
		if label.begins_with("Central stairwell edge coping") and mesh.mesh.get_aabb().end.y>10.7:
			if not require(open_edges(mesh.mesh)==0,"Roof coping still has an open end"): return
		if label.begins_with("L1 inner sofa background") or label.begins_with("L1 outer hallway display") or label.begins_with("L1 rear end oak flute"):
			if not require(mesh.mesh.get_aabb().end.y<=4.2991,"Lower-storey wall/return protrudes through landing: "+label): return
		if label.begins_with("Public stair rail post"):
			for floor_y: float in [4.3,7.1,9.9]:
				if absf((originals[mesh] as Mesh).get_aabb().position.y-floor_y-0.05)<0.002:
					if not require(mesh.mesh.get_aabb().position.y<floor_y,"Landing post is suspended above floor"): return
		if (label.begins_with("Public stair L") and "tread" in label):
			if not require(mesh.mesh==originals[mesh], "Approved treads or the upstairs guard wall were replaced"): return
		if "handrail" in label and ("diffuser" in label or "luminous edge" in label):
			var end_angle := -153.0 if "L1" in label else -115.0
			var closest := INF
			for point: Vector3 in mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
				closest=minf(closest,rad_to_deg(atan2(point.z,point.x))-end_angle)
			if not require(closest>=0.0 and closest<0.3,"Light strip does not end inside terminal post"): return
		var extras: Dictionary=mesh.get_meta("extras",{})
		var expected: Array=extras.get("design_lights",[])
		if not expected.is_empty():
			if not require(mesh.find_children("*","Light3D",false,false).size()==expected.size(), "Stair finish lost an authored light source"): return
	var cheek := fixture.find_child("L1 enclosed tread-facing cheek walls and underside", true, false) as MeshInstance3D
	var repaired_parts := 0
	for mesh: MeshInstance3D in originals:
		var label := str(mesh.name)
		if label=="L1 enclosed tread-facing cheek walls and underside" or label.begins_with("L1 high-end rounded plaster corner"):
			repaired_parts+=1
			if not require(mesh.mesh.get_aabb().end.y<=4.2991, "Original L1 component protrudes above the landing: "+label): return
			var before: Mesh=originals[mesh]
			for surface in range(before.get_surface_count()):
				var old := before.surface_get_arrays(surface)
				var now := mesh.mesh.surface_get_arrays(surface)
				if not require(now[Mesh.ARRAY_INDEX]==old[Mesh.ARRAY_INDEX], "Landing repair changed original surface topology"): return
				for i in range(old[Mesh.ARRAY_VERTEX].size()):
					var p: Vector3=old[Mesh.ARRAY_VERTEX][i]
					var q: Vector3=now[Mesh.ARRAY_VERTEX][i]
					if not require(q.is_equal_approx(Vector3(p.x,minf(p.y,4.299),p.z)), "Landing repair moved geometry outside the original end-height correction"): return
	if not require(repaired_parts==3, "Missing original sloping cheek or two rounded corners"): return
	if not require(fixture.find_children("StairFinish*", "MeshInstance3D", true, false).is_empty(), "Added concealment boards remain at the landing"): return
	var finished_screens := 0
	for mesh: MeshInstance3D in originals:
		var label := str(mesh.name)
		if not (label.begins_with("Public stair L2 low screen") or label.begins_with("Public stair L3 low screen")): continue
		finished_screens+=1
		var landing := 7.1 if "L2" in label else 9.9
		var floor_y := landing-2.8
		var before: Mesh=originals[mesh]
		if not require(mesh.mesh.get_aabb().end.y<=landing-0.0005,"Upper screen end protrudes into landing: "+label): return
		for surface in range(before.get_surface_count()):
			var old := before.surface_get_arrays(surface)
			var now := mesh.mesh.surface_get_arrays(surface)
			if not require(old[Mesh.ARRAY_INDEX]==now[Mesh.ARRAY_INDEX],"Lost original closed screen topology"): return
			for i in range(old[Mesh.ARRAY_VERTEX].size()):
				var p: Vector3=old[Mesh.ARRAY_VERTEX][i]
				var q: Vector3=now[Mesh.ARRAY_VERTEX][i]
				if not require(is_equal_approx(p.x,q.x) and is_equal_approx(p.z,q.z),"Screen was shifted sideways away from its rail"): return
				if p.y<=floor_y+0.231:
					if not require(q.y<=floor_y,"Screen foot protrudes on lower platform: "+label): return
	if not require(finished_screens==4,"Missing upper-floor screen pair"): return
	var physics := PHYSICS.new()
	fixture.add_child(physics)
	physics.build(fixture)
	for mesh: MeshInstance3D in originals:
		if not PHYSICS.uses_concave_collision(mesh): continue
		var body: StaticBody3D
		for candidate: StaticBody3D in physics.find_children("*", "StaticBody3D", true, false):
			if candidate.get_meta("source_node", "")==str(mesh.name): body=candidate
		if not require(body!=null, "Original collision owner disappeared: "+str(mesh.name)): return
		var collision := body.get_child(0) as CollisionShape3D
		if not require((collision.shape as ConcavePolygonShape3D).get_faces()==PHYSICS.collision_faces(originals[mesh]), "Stair rendering repair changed the original collision triangles"): return
	var repaired := cheek.mesh
	preload("res://rooms/estate/estate_stair_finish.gd").apply(fixture)
	if not require(fixture.find_children("LandingTerminalPost*","MeshInstance3D",true,false).size()==2,"Repeated setup duplicated terminal posts"): return
	if not require(cheek.mesh==repaired and fixture.find_children("StairFinish*", "MeshInstance3D", true, false).is_empty(), "Repeated presentation setup duplicates or re-trims the stair repair"): return
	fixture.free()
	print("PASS three flights stair finish: closed round rail caps, original slope/corner end heights, no added boards, exact original collision triangles")
	quit(0)

func open_edges(mesh: Mesh) -> int:
	var counts: Dictionary = {}
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		for i in range(0, indices.size(), 3):
			for edge in range(3):
				var a := points[indices[i+edge]].snapped(Vector3.ONE*0.00001)
				var b := points[indices[i+(edge+1)%3]].snapped(Vector3.ONE*0.00001)
				if a==b: continue
				var key := str(a)+":"+str(b) if str(a)<str(b) else str(b)+":"+str(a)
				counts[key] = int(counts.get(key,0))+1
	var count := 0
	for uses: int in counts.values():
		if uses==1: count+=1
	return count
