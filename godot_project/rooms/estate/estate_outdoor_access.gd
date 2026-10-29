extends Node3D

const LAYERS := preload("res://runtime/world/collision_layers.gd")
const GRID := 0.1
const MASK_ORIGIN := Vector2(-51,-45)
const MASK_WIDTH := 1020
const MASK_HEIGHT := 1020
const EDGE_CELL := 0.25
const SURFACE_CELL := 2.0
const BOTTOM := -1.0
const TOP := 3.0
const SURFACES := [
	"ROAD REF • ring continuous warm-grey stone bed",
	"CY R003 circular waterfront platform closed foundation",
	"Flower preview | CY R003 reference seven-petal stone and ring-material connector",
	"Flower preview | CY R002 curved entrance lower tread",
	"Flower preview | CY R002 curved entrance upper tread",
]
const LAWN := "CY SHORE solid Continuous lawn with true lake opening"
const LAWN_EXCLUSIONS := [
	"COMPLETE Building garden island",
	"COMPLETE Rear woodland ground to road edge",
	"COMPLETE Scalloped front flower border",
	"CY R003 corrected CY R002 lakeside returned solid planting bank",
	"CY R003 corrected CY R002 lakeside gently sloping planted shore",
	"CY R003 corrected CY SHORE solid Continuous planted lake bank",
]
var boundary_segments: Array[Dictionary] = []
var source_names := PackedStringArray()
var _surfaces: Array[Dictionary] = []
var _outdoor_surfaces: Array[Dictionary] = []
var _lawns: Array[Dictionary] = []
var _lawn_exclusions: Array[Dictionary] = []
var _closed_facilities: Array[Dictionary] = []
var _plant_surfaces: Array[Dictionary] = []
var plant_source_groups := 0
var plant_instance_count := 0
var _raw_mask := PackedByteArray()
var _connected_mask := PackedByteArray()
var _edges: Array[Dictionary] = []
var _edge_index: Dictionary = {}
var _surface_indices: Dictionary = {}
var loaded_precompiled := false

func load_precompiled(data: Resource) -> void:
	var buckets := [_surfaces,_outdoor_surfaces,_lawns,_lawn_exclusions,_closed_facilities,_plant_surfaces]
	for i in range(buckets.size()):
		buckets[i].assign(data.activity_buckets[i]["surfaces"])
		for surface: Dictionary in buckets[i]:_index_surface(surface,i)
	_raw_mask=data.raw_mask
	_connected_mask=data.connected_mask
	boundary_segments.assign(data.boundary_segments)
	source_names=data.source_names
	_install_boundary(data.boundary_shape)
	loaded_precompiled=true
	print("OUTDOOR_ACCESS_LOADED segments=",boundary_segments.size())

func capture_precompiled(data: Resource) -> void:
	for bucket: Array in [_surfaces,_outdoor_surfaces,_lawns,_lawn_exclusions,_closed_facilities,_plant_surfaces]:
		data.activity_buckets.append({"surfaces":bucket})
	data.raw_mask=_raw_mask
	data.connected_mask=_connected_mask
	data.boundary_segments=boundary_segments
	data.source_names=source_names
	data.boundary_shape=get_node("OutdoorMovementBoundary").get_child(0).shape

func build(estate: Node3D) -> bool:
	var ground_regions := PackedStringArray()
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		var extras: Dictionary = mesh.get_meta("extras",{})
		var source := str(extras.get("source_name",mesh.name))
		var ground_region := str(extras.get("landscape_ground_region",""))
		if ground_region in ["lawn","planting","woodland"]:
			# These are actual ground faces authored from the approved outline.
			# Plant leaves no longer reconstruct or cut this surface at startup.
			var bucket: Array[Dictionary] = _lawns if ground_region == "lawn" else _lawn_exclusions
			var outlines: Array[PackedVector2Array] = []
			if ground_region == "woodland":
				outlines=_top_outlines(mesh,0,0.25)
			else:
				# The boundary is saved on the same mesh that it triangulates.
				# Reversing dense internal scanline seams is unnecessary and can
				# produce touching cycles that native polygon queries misclassify.
				for raw: Dictionary in extras.get("landscape_ground_boundary_xz",[]):
					var ring := PackedVector2Array()
					for point: Array in raw["points"]:
						var world := mesh.global_transform*Vector3(point[0],0,point[1])
						ring.append(Vector2(world.x,world.z))
					outlines.append(ring)
				if outlines.is_empty():
					push_error("Missing authored ground mesh boundary: "+ground_region)
					return false
			_add_surface(outlines,bucket)
			ground_regions.append(ground_region)
			source_names.append(source)
			continue
		if bool(extras.get("forestTrail",false)):
			# The real mesh includes flared ring joins and the merged branch.
			# Reconstructing butt caps from a centreline would narrow those joins.
			for surface in range(mesh.mesh.get_surface_count()):
				# Main road and return spur overlap in this one mesh surface.
				# They are separate solid outlines, not an outer ring and a hole.
				for outline: PackedVector2Array in _top_outlines(mesh,surface):
					_add_surface([outline],_surfaces,true)
			source_names.append(source)
		elif source in SURFACES:
			# The skirt's actual top includes ivory/sage paving surfaces. Its
			# structural bed alone contains grout gaps, sides and an underside.
			var count := mesh.mesh.get_surface_count()
			for surface in range(count):
				var outlines := _top_outlines(mesh,surface)
				_add_surface(outlines,_surfaces,true)
				if source == "ROAD REF • ring continuous warm-grey stone bed":
					# Lawn inside the ring is protected planting, except for the
					# separately included plaza and real building/door footprints.
					for outline: PackedVector2Array in outlines:
						_add_surface([outline],_lawn_exclusions)
			source_names.append(source)
		elif source == LAWN:
			_add_surface(_top_outlines(mesh,0),_lawns)
			source_names.append(source)
		elif source in LAWN_EXCLUSIONS:
			_add_surface(_top_outlines(mesh,0,0.25),_lawn_exclusions)
			source_names.append(source)
		elif source.begins_with("CY R001 fountain ") or source.begins_with("CY R001 spillway ") or source.begins_with("ROAD REF • fountain "):
			for surface in range(mesh.mesh.get_surface_count()):
				# Basin loops describe a whole closed facility, including its
				# water, coping and outlet; their inner rings are not activity space.
				for outline: PackedVector2Array in _top_outlines(mesh,surface,0.25):
					_add_surface([outline],_closed_facilities)
		elif source == "Central L1 rounded garden entrance":
			# The portal bridges the small seam between the raised indoor slab
			# and curved outdoor tread. Derive its crossing from the real frame.
			var bounds := mesh.global_transform * mesh.get_aabb()
			var back := bounds.position.z-bounds.size.z
			var front := bounds.end.z+bounds.size.z
			_add_surface([PackedVector2Array([Vector2(bounds.position.x,back),Vector2(bounds.end.x,back),Vector2(bounds.end.x,front),Vector2(bounds.position.x,front)])],_surfaces)
		elif source == "Central L1 fitted complete floor" or "continuous lower floor" in source or "flush threshold" in source:
			# Actual indoor floors/door links stay accessible. The surrounding
			# soil island is not a substitute for these authored footprints.
			for surface in range(mesh.mesh.get_surface_count()):
				_add_surface(_top_outlines(mesh,surface),_surfaces)
	if _lawns.is_empty():
		push_error("Missing authored lawn footprint: "+str(source_names))
		return false
	for role: String in ["lawn","planting","woodland"]:
		if not ground_regions.has(role):
			push_error("Missing authored ground region: "+role)
			return false
	_build_connected_mask()
	_index_edges()
	print("OUTDOOR_SOURCE_EDGES candidates=",_edges.size())
	_index_connectivity_cuts()
	_build_boundary()
	print("OUTDOOR_ACCESS sources=",source_names.size()," masks=",_surfaces.size()," boundary_segments=",boundary_segments.size())
	return true

func _add_authored_plants(estate: Node3D) -> bool:
	# The same source matrices and mesh templates drive the actual renderer.
	# Some planted patches have no separate soil slab; their geometry must
	# therefore contribute to the lawn subtraction as well. No hand-drawn
	# triangle, hull, border offset or rectangular plot is introduced.
	var lawn := _rasterize(_lawns)
	var planting := _rasterize(_lawn_exclusions)
	var paving := _rasterize(_surfaces)
	for i in range(lawn.size()): lawn[i]=int(lawn[i]!=0 and planting[i]==0 and paving[i]==0)
	var file := FileAccess.open(CompleteEstateFinal.INSTANCE_SIDECAR_PATH,FileAccess.READ)
	if file==null: return false
	var magic := file.get_buffer(8).get_string_from_ascii()
	var version := file.get_32()
	var groups := file.get_32()
	file.get_32()
	if magic!=CompleteEstateFinal.SIDECAR_MAGIC or version!=1:
		push_error("Invalid source plant instance geometry")
		return false
	var projected: Array[PackedVector2Array] = []
	for _group in range(groups):
		var length := file.get_32();var count := file.get_32()
		var name := file.get_buffer(length).get_string_from_utf8()
		var matrices := file.get_buffer(count*64).to_float32_array()
		var number := name.trim_prefix("__ELFIE_INST_GROUP_").to_int()
		# Plant families in this fixed GLB: trees 0–51 and rocks 82–87 are
		# deliberately separate from groundcover, shrubs, sedges and flowers.
		if not ((number>=52 and number<=81) or (number>=88 and number<=132)): continue
		var template := estate.find_child(name,true,false) as MeshInstance3D
		if template==null or template.mesh==null:
			push_error("Missing source plant mesh: "+name)
			return false
		plant_source_groups+=1
		var local_footprint := _plant_mesh_union(template)
		for instance in range(count):
			var i := instance*16
			var frame := estate.global_transform*Transform3D(Basis(Vector3(matrices[i],matrices[i+1],matrices[i+2]),Vector3(matrices[i+4],matrices[i+5],matrices[i+6]),Vector3(matrices[i+8],matrices[i+9],matrices[i+10])),Vector3(matrices[i+12],matrices[i+13],matrices[i+14]))
			var bounds := frame*template.mesh.get_aabb()
			if not _overlaps_mask(bounds,lawn): continue
			plant_instance_count+=1
			# All source plant instances rotate/scale about their vertical axis.
			# Projection therefore commutes with this exact instance transform;
			# merge the template once instead of repeating every leaf per plant.
			if absf(frame.basis.y.x)>0.000001 or absf(frame.basis.y.z)>0.000001:
				push_error("Source plant transform requires a full 3D projection: "+name)
				return false
			for outline: PackedVector2Array in local_footprint:
				var transformed := PackedVector2Array()
				for point: Vector2 in outline:
					var world := frame*Vector3(point.x,0,point.y)
					transformed.append(Vector2(world.x,world.z))
				projected.append(transformed)
	file.close()
	for outline: PackedVector2Array in _merge_positive_polygons(projected):
		_add_surface([outline],_plant_surfaces)
	print("OUTDOOR_SOURCE_PLANTS groups=",plant_source_groups," edge_instances=",plant_instance_count," projected_surfaces=",_plant_surfaces.size())
	return true

func _plant_mesh_union(mesh: MeshInstance3D) -> Array[PackedVector2Array]:
	var triangles: Array[PackedVector2Array] = []
	for surface in range(mesh.mesh.get_surface_count()):
		var arrays := mesh.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX]!=null else PackedInt32Array()
		var size := vertices.size() if indices.is_empty() else indices.size()
		for i in range(0,size,3):
			var triangle := PackedVector2Array()
			for j in range(3):
				var vertex := vertices[i+j if indices.is_empty() else indices[i+j]]
				triangle.append(Vector2(vertex.x,vertex.z))
			var area := (triangle[1]-triangle[0]).cross(triangle[2]-triangle[0])
			if absf(area)<0.0000001: continue
			if area<0: triangle.reverse()
			triangles.append(triangle)
	return _merge_positive_polygons(triangles)

func _merge_positive_polygons(input: Array[PackedVector2Array]) -> Array[PackedVector2Array]:
	# Exact geometric unions only. If a union has a hole, retain its original
	# overlapping pieces; capping that hole would invent occupied ground.
	var active: Dictionary = {}
	var index: Dictionary = {}
	var serial := 0
	for source: PackedVector2Array in input:
		var polygon := source
		var changed := true
		while changed:
			changed=false
			var bounds := Rect2(polygon[0],Vector2.ZERO)
			for point: Vector2 in polygon: bounds=bounds.expand(point)
			var candidates: Dictionary = {}
			for cell: Vector2i in _cells(bounds.position,bounds.end,SURFACE_CELL):
				for id: int in index.get(cell,[]):
					if active.has(id): candidates[id]=true
			for id: int in candidates:
				var merged := Geometry2D.merge_polygons(polygon,active[id])
				if merged.size()!=1: continue
				polygon=merged[0];active.erase(id);changed=true;break
		active[serial]=polygon
		var bounds := Rect2(polygon[0],Vector2.ZERO)
		for point: Vector2 in polygon: bounds=bounds.expand(point)
		for cell: Vector2i in _cells(bounds.position,bounds.end,SURFACE_CELL):
			if not index.has(cell): index[cell]=[]
			index[cell].append(serial)
		serial+=1
	var result: Array[PackedVector2Array] = []
	result.assign(active.values())
	return result

func _overlaps_mask(bounds: AABB,mask: PackedByteArray) -> bool:
	var x0 := maxi(0,floori((bounds.position.x-MASK_ORIGIN.x)/GRID))
	var x1 := mini(MASK_WIDTH,ceili((bounds.end.x-MASK_ORIGIN.x)/GRID))
	var z0 := maxi(0,floori((bounds.position.z-MASK_ORIGIN.y)/GRID))
	var z1 := mini(MASK_HEIGHT,ceili((bounds.end.z-MASK_ORIGIN.y)/GRID))
	for z in range(z0,z1):
		for x in range(x0,x1):
			if mask[z*MASK_WIDTH+x]!=0: return true
	return false

func _rasterize(surfaces: Array[Dictionary]) -> PackedByteArray:
	var mask := PackedByteArray()
	mask.resize(MASK_WIDTH*MASK_HEIGHT)
	for surface: Dictionary in surfaces:
		var bounds: Rect2 = surface["bounds"]
		var first := maxi(0,floori((bounds.position.y-MASK_ORIGIN.y)/GRID))
		var last := mini(MASK_HEIGHT,ceili((bounds.end.y-MASK_ORIGIN.y)/GRID))
		for z in range(first,last):
			var y := MASK_ORIGIN.y+(z+0.5)*GRID
			var crossings: Array[Vector2] = []
			for ring: PackedVector2Array in surface["rings"]:
				for j in range(ring.size()):
					var a := ring[j];var b := ring[(j+1)%ring.size()]
					if (a.y>y)!=(b.y>y): crossings.append(Vector2(a.x+(y-a.y)*(b.x-a.x)/(b.y-a.y),1 if b.y>a.y else -1))
			crossings.sort_custom(func(a: Vector2,b: Vector2) -> bool: return a.x<b.x)
			var winding := 0
			for j in range(crossings.size()-1):
				winding+=int(crossings[j].y)
				if winding==0: continue
				var left := maxi(0,ceili((crossings[j].x-MASK_ORIGIN.x)/GRID-0.5))
				var right := mini(MASK_WIDTH,ceili((crossings[j+1].x-MASK_ORIGIN.x)/GRID-0.5))
				for x in range(left,right): mask[z*MASK_WIDTH+x]=1
	return mask

func _build_connected_mask() -> void:
	# Geometry supplies the footprints; connectivity and the actual 0.3 m
	# navigation radius remove islands and strips no actor can reach. The
	# dilation restores the source edge, rather than moving it to the eroded
	# centre corridor. Recast still applies its own body clearance afterward.
	var paving := _rasterize(_surfaces)
	var lawn := _rasterize(_lawns)
	var planting := _rasterize(_lawn_exclusions+_plant_surfaces)
	var facilities := _rasterize(_closed_facilities)
	_raw_mask.resize(MASK_WIDTH*MASK_HEIGHT)
	for i in range(_raw_mask.size()):
		_raw_mask[i]=int((paving[i]!=0 or (lawn[i]!=0 and planting[i]==0)) and facilities[i]==0)
	var core := PackedByteArray()
	core.resize(_raw_mask.size())
	var erosion: Array[Vector2i] = []
	var restore: Array[Vector2i] = []
	for z in range(-5,6):
		for x in range(-5,6):
			if x*x+z*z<=9: erosion.append(Vector2i(x,z))
			if x*x+z*z<=20: restore.append(Vector2i(x,z))
	for z in range(3,MASK_HEIGHT-3):
		for x in range(3,MASK_WIDTH-3):
			var i := z*MASK_WIDTH+x
			if _raw_mask[i]==0: continue
			var clear := true
			for offset: Vector2i in erosion:
				if _raw_mask[i+offset.y*MASK_WIDTH+offset.x]==0:
					clear=false;break
			if clear: core[i]=1
	var seed := Vector2i((Vector2(0,20)-MASK_ORIGIN)/GRID)
	var queue := PackedInt32Array([seed.y*MASK_WIDTH+seed.x])
	assert(core[queue[0]]==1,"Approved plaza must seed the outdoor access component")
	core[queue[0]]=2
	var head := 0
	while head<queue.size():
		var i := queue[head];head+=1
		for next: int in [i-1,i+1,i-MASK_WIDTH,i+MASK_WIDTH]:
			if next>=0 and next<core.size() and core[next]==1:
				core[next]=2;queue.append(next)
	_connected_mask.resize(_raw_mask.size())
	for z in range(5,MASK_HEIGHT-5):
		for x in range(5,MASK_WIDTH-5):
			var i := z*MASK_WIDTH+x
			if _raw_mask[i]==0: continue
			for offset: Vector2i in restore:
				if core[i+offset.y*MASK_WIDTH+offset.x]==2:
					_connected_mask[i]=1;break
	print("OUTDOOR_CONNECTED reachable_body_cells=",queue.size())

func _connected_contains(point: Vector2) -> bool:
	if _connected_mask.is_empty(): return true
	var cell := Vector2i((point-MASK_ORIGIN)/GRID)
	if cell.x<1 or cell.y<1 or cell.x>=MASK_WIDTH-1 or cell.y>=MASK_HEIGHT-1: return false
	var i := cell.y*MASK_WIDTH+cell.x
	if _raw_mask[i]!=0: return _connected_mask[i]!=0
	# A source contour can pass through a cell whose centre is outside it.
	# Retain that geometric edge without turning it into raster stair steps.
	for z in range(-1,2):
		for x in range(-1,2):
			if _connected_mask[i+z*MASK_WIDTH+x]!=0: return true
	return false

func _cell_allowed(x: int,z: int) -> bool:
	var col := x-roundi(MASK_ORIGIN.x/GRID)
	var row := z-roundi(MASK_ORIGIN.y/GRID)
	return col>=0 and col<MASK_WIDTH and row>=0 and row<MASK_HEIGHT and _connected_mask[row*MASK_WIDTH+col]!=0

func _index_connectivity_cuts() -> void:
	# Only newly closed necks need raster edges. Everywhere else the physical
	# boundary continues to use the intersected authored mesh contours.
	for z in range(1,MASK_HEIGHT-1):
		for x in range(1,MASK_WIDTH-1):
			var i := z*MASK_WIDTH+x
			if _raw_mask[i]==0: continue
			for offset: Vector2i in [Vector2i.RIGHT,Vector2i.DOWN]:
				var next := i+offset.y*MASK_WIDTH+offset.x
				if _raw_mask[next]==0 or _connected_mask[i]==_connected_mask[next]: continue
				var a := MASK_ORIGIN+Vector2(x+offset.x,z+offset.y)*GRID
				var b := a+Vector2(offset.y,offset.x)*GRID
				var index := _edges.size();_edges.append({"a":a,"b":b,"bounds":Rect2(a,Vector2.ZERO).expand(b).grow(0.00001)})
				for cell: Vector2i in _cells(a,b):
					if not _edge_index.has(cell): _edge_index[cell]=[]
					_edge_index[cell].append(index)

func _add_surface(rings: Array[PackedVector2Array], bucket: Array[Dictionary], outdoor: bool = false) -> void:
	if rings.is_empty():return
	var bounds := Rect2(rings[0][0],Vector2.ZERO)
	for ring: PackedVector2Array in rings:
		for point: Vector2 in ring: bounds=bounds.expand(point)
	var native_rings: Array[Dictionary] = []
	for ring: PackedVector2Array in rings:
		var ring_bounds := Rect2(ring[0],Vector2.ZERO)
		var area := 0.0
		for j in range(ring.size()):
			ring_bounds=ring_bounds.expand(ring[j])
			area+=ring[j].cross(ring[(j+1)%ring.size()])
		native_rings.append({"points":ring,"bounds":ring_bounds.grow(0.00001),"weight":1 if area>0 else -1})
	var surface := {"rings":rings,"bounds":bounds.grow(0.002),"native_rings":native_rings}
	bucket.append(surface)
	_index_surface(surface,_bucket_id(bucket))
	if outdoor:
		_outdoor_surfaces.append(surface)
		_index_surface(surface,1)

func contains_point(point: Vector2) -> bool:
	return _connected_contains(point) and (_contains(_surfaces,point) or _front_lawn_contains(point)) and not _closed_plot_contains(point)

func contains_outdoor_point(point: Vector2) -> bool:
	return _connected_contains(point) and (_contains(_outdoor_surfaces,point) or _front_lawn_contains(point)) and not _closed_plot_contains(point)

func _closed_plot_contains(point: Vector2) -> bool:
	return _contains(_closed_facilities,point)

func _front_lawn_contains(point: Vector2) -> bool:
	return _contains(_lawns,point) and not _contains(_lawn_exclusions,point) and not _contains(_plant_surfaces,point)

func _bucket_id(bucket: Array[Dictionary]) -> int:
	var buckets := [_surfaces,_outdoor_surfaces,_lawns,_lawn_exclusions,_closed_facilities,_plant_surfaces]
	for i in range(buckets.size()):
		if is_same(bucket,buckets[i]): return i
	return -1

func _index_surface(surface: Dictionary,bucket: int) -> void:
	if bucket<0: return
	if not _surface_indices.has(bucket): _surface_indices[bucket]={}
	var index: Dictionary = _surface_indices[bucket]
	var bounds: Rect2 = surface["bounds"]
	for cell: Vector2i in _cells(bounds.position,bounds.end,SURFACE_CELL):
		if not index.has(cell): index[cell]=[]
		index[cell].append(surface)

func _contains(surfaces: Array[Dictionary],point: Vector2) -> bool:
	var candidates: Array = surfaces
	var bucket := _bucket_id(surfaces)
	if bucket>=0:
		candidates=(_surface_indices.get(bucket,{}) as Dictionary).get(Vector2i(floori(point.x/SURFACE_CELL),floori(point.y/SURFACE_CELL)),[])
	for surface: Dictionary in candidates:
		if not (surface["bounds"] as Rect2).has_point(point):continue
		var winding := 0
		for ring: Dictionary in surface["native_rings"]:
			if (ring["bounds"] as Rect2).has_point(point) and Geometry2D.is_point_in_polygon(point,ring["points"]): winding+=int(ring["weight"])
		if winding!=0:return true
	return false

func _top_outlines(mesh: MeshInstance3D,surface: int,minimum_up: float = 0.7) -> Array[PackedVector2Array]:
	return _projected_outlines(mesh,surface,mesh.global_transform,minimum_up)

func _projected_outlines(mesh: MeshInstance3D,surface: int,frame: Transform3D,minimum_up: float) -> Array[PackedVector2Array]:
	var arrays := mesh.mesh.surface_get_arrays(surface)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL] if arrays[Mesh.ARRAY_NORMAL]!=null else PackedVector3Array()
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX]!=null else PackedInt32Array()
	var size := vertices.size() if indices.is_empty() else indices.size()
	var edges: Dictionary = {}
	var points: Dictionary = {}
	var normal_frame := frame.basis.inverse().transposed()
	for offset in range(0,size,3):
		var triangle := PackedVector3Array()
		var normal := Vector3.ZERO
		for j in range(3):
			var index := offset+j if indices.is_empty() else indices[offset+j]
			triangle.append(frame*vertices[index])
			if not normals.is_empty(): normal+=normal_frame*normals[index]
		if normals.is_empty(): normal=-(triangle[1]-triangle[0]).cross(triangle[2]-triangle[0])
		if normal.normalized().y<minimum_up: continue
		var keys: Array[Vector2i] = []
		for vertex: Vector3 in triangle:
			var key := Vector2i(roundi(vertex.x*1000),roundi(vertex.z*1000))
			keys.append(key);points[key]=Vector2(key)*0.001
		var area := Vector2(keys[1]-keys[0]).cross(Vector2(keys[2]-keys[0]))
		if area==0: continue
		if area<0: keys.reverse()
		for j in range(3):
			var a := keys[j];var b := keys[(j+1)%3]
			var key := str(a)+"/"+str(b)
			var reverse := str(b)+"/"+str(a)
			if edges.has(reverse):
				edges[reverse]["count"]-=1
				if edges[reverse]["count"]==0: edges.erase(reverse)
			elif edges.has(key): edges[key]["count"]+=1
			else: edges[key]={"a":a,"b":b,"count":1}
	var outgoing: Dictionary = {}
	for edge: Dictionary in edges.values():
		if not outgoing.has(edge["a"]): outgoing[edge["a"]]=[]
		outgoing[edge["a"]].append(edge["b"])
	var rings: Array[PackedVector2Array] = []
	while not edges.is_empty():
		var first: Dictionary = edges.values()[0]
		var start: Vector2i = first["a"]
		var current := start
		var ring := PackedVector2Array()
		var closed := false
		while true:
			ring.append(points[current])
			var next := current
			for candidate: Vector2i in outgoing.get(current,[]):
				var key := str(current)+"/"+str(candidate)
				if not edges.has(key): continue
				next=candidate;edges[key]["count"]-=1
				if edges[key]["count"]==0: edges.erase(key)
				break
			if next==current: break
			current=next
			if current==start: closed=true;break
		if closed and ring.size()>=3: rings.append_array(_split_touching_cycles(ring))
		else:
			push_error("Open projected source surface: "+str(mesh.name))
			break
	return rings

func _split_touching_cycles(ring: PackedVector2Array) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []
	var stack := PackedVector2Array()
	var positions: Dictionary = {}
	for i in range(ring.size()+1):
		var point := ring[i%ring.size()]
		if positions.has(point):
			var start: int = positions[point]
			var cycle := stack.slice(start)
			if cycle.size()>=3: result.append(cycle)
			for j in range(start+1,stack.size()): positions.erase(stack[j])
			stack.resize(start+1)
		else:
			positions[point]=stack.size();stack.append(point)
	return result

func _edge_near_access(a: Vector2,b: Vector2) -> bool:
	var steps := maxi(1,ceili(a.distance_to(b)/GRID))
	for j in range(steps+1):
		var cell := Vector2i((a.lerp(b,float(j)/steps)-MASK_ORIGIN)/GRID)
		for z in range(maxi(0,cell.y-1),mini(MASK_HEIGHT,cell.y+2)):
			for x in range(maxi(0,cell.x-1),mini(MASK_WIDTH,cell.x+2)):
				if _connected_mask[z*MASK_WIDTH+x]!=0: return true
	return false

func _index_edges() -> void:
	for surface: Dictionary in _surfaces + _lawns + _lawn_exclusions + _plant_surfaces + _closed_facilities:
		for ring: PackedVector2Array in surface["rings"]:
			for j in range(ring.size()):
				var edge := {"a":ring[j],"b":ring[(j+1)%ring.size()],"bounds":Rect2(ring[j],Vector2.ZERO).expand(ring[(j+1)%ring.size()]).grow(0.00001)}
				if (edge["a"] as Vector2).distance_to(edge["b"])<0.002:continue
				if not _edge_near_access(edge["a"],edge["b"]): continue
				var index := _edges.size();_edges.append(edge)
				for cell: Vector2i in _cells(edge["a"],edge["b"]):
					if not _edge_index.has(cell):_edge_index[cell]=[]
					_edge_index[cell].append(index)

func _cells(a: Vector2,b: Vector2,cell_size: float = EDGE_CELL) -> Array[Vector2i]:
	var result: Array[Vector2i] = []
	for x in range(floori(minf(a.x,b.x)/cell_size),floori(maxf(a.x,b.x)/cell_size)+1):
		for y in range(floori(minf(a.y,b.y)/cell_size),floori(maxf(a.y,b.y)/cell_size)+1):result.append(Vector2i(x,y))
	return result

func _build_boundary() -> void:
	var faces := PackedVector3Array()
	var seen: Dictionary = {}
	for edge: Dictionary in _edges:
		var a: Vector2 = edge["a"];var b: Vector2 = edge["b"]
		var candidates: Dictionary = {}
		for cell: Vector2i in _cells(a,b):
			for index: int in _edge_index.get(cell,[]):candidates[index]=true
		var cuts: Array[float] = [0.0,1.0]
		for index: int in candidates:
			var other: Dictionary = _edges[index]
			if not (edge["bounds"] as Rect2).intersects(other["bounds"]): continue
			var hit: Variant = Geometry2D.segment_intersects_segment(a,b,other["a"],other["b"])
			if hit is Vector2:cuts.append(clampf((hit-a).dot(b-a)/(b-a).length_squared(),0.0,1.0))
		cuts.sort()
		for j in range(1,cuts.size()):
			var p := a.lerp(b,cuts[j-1]);var q := a.lerp(b,cuts[j])
			if p.distance_to(q)<0.002:continue
			var middle := (p+q)*0.5;var normal := (q-p).orthogonal().normalized()*0.005
			if contains_point(middle+normal)==contains_point(middle-normal):continue
			var pk := str(Vector2i(p*1000));var qk := str(Vector2i(q*1000))
			var key := pk+"/"+qk if pk<qk else qk+"/"+pk
			if seen.has(key):continue
			seen[key]=true;boundary_segments.append({"a":p,"b":q})
			var lo_a := Vector3(p.x,BOTTOM,p.y);var lo_b := Vector3(q.x,BOTTOM,q.y)
			var hi_a := Vector3(p.x,TOP,p.y);var hi_b := Vector3(q.x,TOP,q.y)
			faces.append_array(PackedVector3Array([lo_a,lo_b,hi_b,lo_a,hi_b,hi_a]))
	var shape := ConcavePolygonShape3D.new();shape.set_faces(faces);shape.backface_collision=true
	_install_boundary(shape)

func _install_boundary(shape: ConcavePolygonShape3D) -> void:
	var body := StaticBody3D.new()
	body.name="OutdoorMovementBoundary";body.collision_layer=LAYERS.MOVEMENT_BOUNDARY;body.collision_mask=0
	add_child(body);body.global_transform=Transform3D.IDENTITY
	var collision := CollisionShape3D.new();collision.shape=shape;body.add_child(collision)

func restrict_navigation(data: NavigationMeshSourceGeometryData3D, bounds: AABB) -> void:
	# Denied strips cover only the ground storey. Authored indoor floors and
	# door links remain included; upper rooms/terraces retain their geometry.
	var x0 := floori(bounds.position.x/GRID);var x1 := ceili(bounds.end.x/GRID)
	var z0 := floori(bounds.position.z/GRID);var z1 := ceili(bounds.end.z/GRID)
	var strips := 0
	for z in range(z0,z1):
		var start := x0
		while start<x1:
			if _cell_allowed(start,z):
				start+=1;continue
			var end := start+1
			while end<x1 and not _cell_allowed(end,z):end+=1
			var polygon := PackedVector3Array([Vector3(start*GRID,0,z*GRID),Vector3(end*GRID,0,z*GRID),Vector3(end*GRID,0,(z+1)*GRID),Vector3(start*GRID,0,(z+1)*GRID)])
			data.add_projected_obstruction(polygon,-2.0,5.0,false)
			strips+=1;start=end
	print("OUTDOOR_NAV_DENIED strips=",strips)

func retain_reachable_navigation(nav: NavigationMesh) -> void:
	# Check baked height/obstacles too: a connected 2D footprint alone cannot
	# distinguish a rock top or an island cut off by the real scene colliders.
	# Use Godot's own path connectivity, on a short-lived synchronous map.
	var map := NavigationServer3D.map_create()
	NavigationServer3D.map_set_cell_size(map,nav.cell_size)
	NavigationServer3D.map_set_cell_height(map,nav.cell_height)
	NavigationServer3D.map_set_use_async_iterations(map,false)
	NavigationServer3D.map_set_active(map,true)
	var region := NavigationServer3D.region_create()
	NavigationServer3D.region_set_use_async_iterations(region,false)
	NavigationServer3D.region_set_navigation_mesh(region,nav)
	NavigationServer3D.region_set_map(region,map)
	NavigationServer3D.map_force_update(map)
	assert(NavigationServer3D.region_get_iteration_id(region)>0 and NavigationServer3D.map_get_iteration_id(map)>0,"Connectivity inspection must synchronize before pruning")
	var seed := NavigationServer3D.map_get_closest_point(map,Vector3(0,0.1,20))
	assert(seed.distance_to(Vector3(0,0.1,20))<0.5,"Connectivity seed must remain on the approved plaza")
	var vertices := nav.get_vertices()
	var retained: Array[PackedInt32Array] = []
	var removed := 0
	for i in range(nav.get_polygon_count()):
		var polygon := nav.get_polygon(i)
		var center := Vector3.ZERO
		var high := -INF
		for index: int in polygon:
			center+=vertices[index];high=maxf(high,vertices[index].y)
		center/=polygon.size()
		if high<=1.4 and contains_outdoor_point(Vector2(center.x,center.z)):
			var path := NavigationServer3D.map_get_path(map,seed,center,true)
			if path.is_empty() or path[-1].distance_to(center)>0.15:
				removed+=1;continue
		retained.append(polygon)
	NavigationServer3D.free_rid(region)
	NavigationServer3D.free_rid(map)
	if removed>0:
		nav.clear_polygons()
		for polygon: PackedInt32Array in retained: nav.add_polygon(polygon)
	print("OUTDOOR_NAV_UNREACHABLE removed_polygons=",removed)
