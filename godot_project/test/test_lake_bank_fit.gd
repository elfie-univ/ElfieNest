extends SceneTree
## Compare the rendered water footprint with a fresh section of the physical solids.

const GROUND := "res://nest/courtyard/parts/ground/shared-ground.glb"
const FOUNTAIN := "res://nest/courtyard/parts/waterside/fountain.glb"
const LAKE := "res://nest/courtyard/parts/waterside/lake.glb"
const HEIGHT := -0.38999998569488525
const SOLIDS := ["CY R003 circular waterfront platform closed foundation", "CY R001 spillway north continuous side wall", "CY R001 spillway south continuous side wall", "CY R001 spillway sealed trough bed", "CY R001 spillway supporting outlet face"]

func _initialize() -> void: call_deferred("run")

static func area(polygon: PackedVector2Array) -> float:
	var sum := 0.0
	for i: int in polygon.size():
		var a := polygon[i]
		var b := polygon[(i+1)%polygon.size()]
		sum += float(a.x)*float(b.y)-float(a.y)*float(b.x)
	return absf(sum)*0.5

static func local_pose(scene_root: Node3D, node: Node3D) -> Transform3D:
	var pose := node.transform
	var parent := node.get_parent() as Node3D
	while parent != null and parent != scene_root:
		pose=parent.transform*pose
		parent=parent.get_parent() as Node3D
	return pose

static func link_edge(graph: Dictionary, a: Vector2i, b: Vector2i) -> void:
	if a==b:return
	if not graph.has(a):graph[a]=[]
	if not graph.has(b):graph[b]=[]
	if b not in graph[a]:graph[a].append(b)
	if a not in graph[b]:graph[b].append(a)

static func trace(graph: Dictionary) -> Dictionary:
	for point: Vector2i in graph:
		if graph[point].size()!=2:return {"error":"A bank/water boundary has a dangling or branched edge"}
	var remaining:=graph.duplicate()
	var polygons:=[]
	while not remaining.is_empty():
		var first: Vector2i=remaining.keys()[0]
		var previous:=first
		var point:=first
		var polygon:=PackedVector2Array()
		while true:
			polygon.append(Vector2(float(point.x)/100000.0,float(point.y)/100000.0))
			remaining.erase(point)
			var options: Array=graph[point]
			var next: Vector2i=options[0] if options[0]!=previous else options[1]
			previous=point
			point=next
			if point==first:break
			if not remaining.has(point):return {"error":"A bank/water boundary folds back"}
		polygons.append(polygon)
	return {"error":"", "polygons":polygons}

static func key(x: float,z: float) -> Vector2i:
	return Vector2i(roundi(x*100000.0),roundi(z*100000.0))

static func render_faces(mesh: Mesh) -> PackedVector3Array:
	# Read render arrays directly; the triangle collision cache welds nearby points.
	var faces:=PackedVector3Array()
	for surface: int in mesh.get_surface_count():
		var arrays:=mesh.surface_get_arrays(surface)
		var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
		if indices.is_empty():faces.append_array(points)
		else:
			for index: int in indices:faces.append(points[index])
	return faces

static func section(meshes: Array[MeshInstance3D], scene_root: Node3D) -> Dictionary:
	var graph:={}
	for mesh:MeshInstance3D in meshes:
		var faces:=render_faces(mesh.mesh)
		var pose:=local_pose(scene_root,mesh)
		for i: int in range(0,faces.size(),3):
			var triangle:=[pose*faces[i],pose*faces[i+1],pose*faces[i+2]]
			var hits:=[]
			for j: int in 3:
				var a: Vector3=triangle[j]
				var b: Vector3=triangle[(j+1)%3]
				var da:=float(a.y)-HEIGHT
				var db:=float(b.y)-HEIGHT
				if absf(da)<0.00000001:hits.append(key(a.x,a.z))
				if da*db<0.0:
					var t:=da/(da-db)
					hits.append(key(float(a.x)+(float(b.x)-float(a.x))*t,float(a.z)+(float(b.z)-float(a.z))*t))
			var unique:=[]
			for point: Vector2i in hits:
				if point not in unique:unique.append(point)
			if unique.size()==2:link_edge(graph,unique[0],unique[1])
	return trace(graph)

static func water_outline(mesh: MeshInstance3D, scene_root: Node3D) -> Dictionary:
	var faces:=render_faces(mesh.mesh)
	var pose:=local_pose(scene_root,mesh)
	var edges:={}
	for i: int in range(0,faces.size(),3):
		var row:=[]
		for j: int in 3:
			var p: Vector3=pose*faces[i+j]
			if absf(p.y-HEIGHT)>0.0000001:return {"error":"Water surfaces do not share one elevation"}
			row.append(key(p.x,p.z))
		for j: int in 3:
			var a: Vector2i=row[j]
			var b: Vector2i=row[(j+1)%3]
			var edge: Array=[a,b] if a.x<b.x or (a.x==b.x and a.y<b.y) else [b,a]
			edges[edge]=int(edges.get(edge,0))+1
	var graph:={}
	for edge: Array in edges:
		if edges[edge]==1:link_edge(graph,edge[0],edge[1])
		elif edges[edge]!=2:return {"error":"Water has duplicate or non-manifold faces","mesh":str(mesh.name),"triangles":faces.size()/3,"edge":str(edge),"incidence":edges[edge]}
	return trace(graph)

static func verify() -> Dictionary:
	var scenes: Array[Node3D]=[]
	var body:=PackedVector2Array()
	var cutters:=[]
	var water:=[]
	var lake_center:=Vector2.ZERO
	for path: String in [GROUND,FOUNTAIN,LAKE]:
		var scene: Node3D=(load(path) as PackedScene).instantiate()
		scenes.append(scene)
		var terrain_meshes:Array[MeshInstance3D]=[]
		for mesh: MeshInstance3D in scene.find_children("*","MeshInstance3D",true,false):
			var source:=str(mesh.get_meta("extras",{}).get("source_name",""))
			if source.begins_with("COMPLETE Building garden island"):
				terrain_meshes.append(mesh)
			elif source in SOLIDS:
				var cut:=section([mesh],scene)
				if not str(cut.error).is_empty():
					for saved: Node in scenes:saved.free()
					return cut
				for polygon: PackedVector2Array in cut.polygons:
					cutters.append(polygon)
			if source in ["COMPLETE Inset natural lake","COMPLETE Inset natural lake receiving under spillway"]:
				var outline:=water_outline(mesh,scene)
				if not str(outline.error).is_empty():
					for saved: Node in scenes:saved.free()
					return outline
				if outline.polygons.size()!=1:
					for saved: Node in scenes:saved.free()
					return {"error":"Each water sheet must have one boundary"}
				water.append(outline.polygons[0])
				if source=="COMPLETE Inset natural lake":
					var bounds:=Rect2(outline.polygons[0][0],Vector2.ZERO)
					for p: Vector2 in outline.polygons[0]:bounds=bounds.expand(p)
					lake_center=bounds.get_center()
		if not terrain_meshes.is_empty():
			var cut:=section(terrain_meshes,scene)
			if not str(cut.error).is_empty():
				for saved:Node in scenes:saved.free()
				return cut
			for polygon:PackedVector2Array in cut.polygons:
				if body.is_empty() or area(polygon)<area(body):body=polygon
	for saved: Node in scenes:saved.free()
	if body.is_empty() or water.size()!=2:return {"error":"Physical lake or water sheet missing"}
	var reference: Array=Array(Geometry2D.merge_polygons(body,body))
	for cutter: PackedVector2Array in cutters:
		var next:=[]
		for polygon: PackedVector2Array in reference:next.append_array(Geometry2D.clip_polygons(polygon,cutter))
		reference=next
	var candidates:=[]
	for polygon: PackedVector2Array in reference:
		if Geometry2D.is_point_in_polygon(lake_center,polygon):candidates.append(polygon)
	if candidates.size()!=1:return {"error":"Cannot identify the connected physical lake"}
	# Boolean intersections create sub-grid coordinates. Compare both outlines on
	# the same 10 micrometre grid used to trace the physical and rendered edges.
	var reference_grid:=PackedVector2Array()
	var quantization_max:=0.0
	for point: Vector2 in candidates[0]:
		var cell:=key(point.x,point.y)
		var snapped:=Vector2(float(cell.x)/100000.0,float(cell.y)/100000.0)
		reference_grid.append(snapped)
		quantization_max=maxf(quantization_max,point.distance_to(snapped))
	var merged:=Geometry2D.merge_polygons(water[0],water[1])
	if merged.size()!=1:return {"error":"Main lake and receiving water do not meet continuously"}
	var overlap:=0.0
	for polygon: PackedVector2Array in Geometry2D.intersect_polygons(water[0],water[1]):overlap+=area(polygon)
	var difference:=0.0
	for polygon: PackedVector2Array in Geometry2D.clip_polygons(merged[0],reference_grid):difference+=area(polygon)
	for polygon: PackedVector2Array in Geometry2D.clip_polygons(reference_grid,merged[0]):difference+=area(polygon)
	if overlap>0.000001:return {"error":"Water sheets overlap","overlap_m2":overlap}
	if difference>0.00001:return {"error":"Water does not match the measured physical basin","difference_m2":difference}
	return {"error":"","reference_area_m2":area(candidates[0]),"difference_m2":difference,"overlap_m2":overlap,"single_connected_surface":true,"inspection_grid_m":0.00001,"reference_quantization_max_m":quantization_max}

func run() -> void:
	var result:=verify()
	if not str(result.error).is_empty():
		push_error(JSON.stringify(result))
		quit(1)
		return
	print("LAKE_PHYSICAL_BANK_FIT_OK ",JSON.stringify(result))
	quit(0)
