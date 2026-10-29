extends RefCounted
## Close and seat original stair components; preserve the imported physical mesh.
const COLLISION_MESH := &"estate_stair_collision_mesh"
const LANDING_END_Y := 4.299
const FINISHED := &"estate_stair_finished"

static func apply(estate: Node3D) -> void:
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var label := str(mesh.name)
		if mesh.has_meta(FINISHED): continue
		var result: Mesh
		if (label.begins_with("L1 clear glass rail panel") and label.ends_with(" 8")) or ("clear infill" in label and label.ends_with("bay 5")):
			var landing := 4.3 if label.begins_with("L1") else (7.1 if "L2" in label else 9.9)
			var local_y := mesh.to_local(estate.to_global(Vector3(0,landing,0))).y
			result=_extend_glass_bottom(mesh.mesh,local_y-0.002)
		elif label.begins_with("Public stair L") and "handrail" in label:
			result=_round_caps(mesh.mesh)
		elif label.begins_with("Central stairwell edge coping") and mesh.mesh.get_aabb().end.y>10.7:
			result=_round_caps(mesh.mesh)
		elif "full stairwell edge 3" in label:
			result=_join_wall_end(mesh.mesh,-153.0 if "L2" in label else -115.0)
		elif label.begins_with("Public stair rail post"):
			for floor_y: float in [4.3,7.1,9.9]:
				if absf(mesh.mesh.get_aabb().position.y-floor_y-0.05)<0.002:
					result=_seat_post(mesh.mesh,floor_y-0.001)
		elif label.begins_with("L1 inner sofa background") or label.begins_with("L1 outer hallway display") or label.begins_with("L1 rear end oak flute"):
			if mesh.mesh.get_aabb().end.y>LANDING_END_Y:
				result=_lower_top(mesh.mesh,LANDING_END_Y)
		elif label=="L1 enclosed tread-facing cheek walls and underside" or label.begins_with("L1 high-end rounded plaster corner"):
			result=_lower_top(mesh.mesh,LANDING_END_Y)
		elif (label.begins_with("Public stair L") and "low screen" in label) or (label.begins_with("L") and "sloping side" in label):
			var flight := 1 if "L1" in label else (2 if "L2" in label else 3)
			var floor_y := 0.3 if flight==1 else (4.3 if flight==2 else 7.1)
			var landing_y := 4.3 if flight==1 else (7.1 if flight==2 else 9.9)
			result=_seat_screen(mesh.mesh,floor_y,landing_y)
		elif (label.begins_with("Working L") and "handrail" in label) or (label.begins_with("L") and "handrail continuous" in label):
			result=_finish_light(mesh.mesh,3.18 if "inner" in label else 4.65,-153.0 if "L1" in label else -115.0)
		if result==null: continue
		mesh.set_meta(COLLISION_MESH,mesh.mesh)
		mesh.set_meta(FINISHED,true)
		mesh.mesh=result
	_add_terminal_posts(estate)
	_fit_terminal_posts(estate)

static func _extend_glass_bottom(source: Mesh, landing_y: float) -> ArrayMesh:
	var result := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		var lower: Dictionary={}
		for p: Vector3 in points:
			var column := Vector2(p.x,p.z).snapped(Vector2.ONE*0.00001)
			lower[column]=minf(float(lower.get(column,INF)),p.y)
		# Extend the existing pane, including its original side faces. Leave the
		# rail edge and all lateral coordinates intact; no separate infill wedge.
		for i in range(points.size()):
			var column := Vector2(points[i].x,points[i].z).snapped(Vector2.ONE*0.00001)
			if absf(points[i].y-float(lower[column]))<0.001:
				points[i].y=minf(points[i].y,landing_y)
		arrays[Mesh.ARRAY_VERTEX]=points
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		result.surface_set_material(surface,source.surface_get_material(surface))
	return result

static func _add_terminal_posts(estate: Node3D) -> void:
	var template := estate.find_child("Public stair rail post",true,false) as MeshInstance3D
	if template==null: return
	for side in range(2):
		var node_name := "LandingTerminalPostInner" if side==0 else "LandingTerminalPostOuter"
		if estate.get_node_or_null(node_name)!=null: continue
		var radius := 3.18 if side==0 else 4.65
		var post := MeshInstance3D.new()
		post.name=node_name
		var cylinder := CylinderMesh.new()
		cylinder.top_radius=0.026
		cylinder.bottom_radius=cylinder.top_radius
		cylinder.height=5.2-4.299
		cylinder.radial_segments=12
		cylinder.material=template.mesh.surface_get_material(0)
		post.mesh=cylinder
		post.layers=template.layers
		# Presentation joinery only: the approved original collision remains
		# owned by the imported stair/wall bodies, not by these two supports.
		estate.add_child(post)
		post.position=Vector3(radius*cos(deg_to_rad(-153.0)),(5.2+4.299)*0.5,radius*sin(deg_to_rad(-153.0)))

static func _seat_post(source: Mesh, base_y: float) -> ArrayMesh:
	var result := ArrayMesh.new()
	var bounds := source.get_aabb()
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		for i in range(points.size()):
			points[i].y=lerpf(base_y,bounds.end.y,(points[i].y-bounds.position.y)/bounds.size.y)
		arrays[Mesh.ARRAY_VERTEX]=points
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		result.surface_set_material(surface,source.surface_get_material(surface))
	return result

static func _seat_screen(source: Mesh, floor_y: float, landing_y: float) -> ArrayMesh:
	return _reshape(source, landing_y-0.001, floor_y)

static func _lower_top(source: Mesh, height: float) -> ArrayMesh:
	return _reshape(source, height, -INF)

static func _reshape(source: Mesh, height: float, floor_y: float) -> ArrayMesh:
	# The original transverse closure already ends at 4.299 m. Use that same
	# end plane for the cheek and its round corners, keeping their existing caps.
	var result := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		var original: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		var points := original.duplicate()
		var normals: PackedVector3Array=arrays[Mesh.ARRAY_NORMAL]
		var indices: PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
		for i in range(points.size()):
			points[i].y=minf(points[i].y,height)
			if is_finite(floor_y):
				# The original 23 cm kick-board rises through the platform at both
				# ends. Seat its lower end below that platform and retain the
				# original closed cross-section, without moving it off the rail axis.
				var weight := smoothstep(floor_y+0.231, floor_y+0.50, original[i].y)
				points[i].y=minf(height,lerpf(minf(original[i].y,floor_y-0.001),original[i].y,weight))
		for i in range(0,indices.size(),3):
			var a := indices[i]
			var b := indices[i+1]
			var c := indices[i+2]
			var normal := (points[c]-points[a]).cross(points[b]-points[a]).normalized()
			if normal.length_squared()<0.5: continue
			if normal.dot(normals[a]+normals[b]+normals[c])<0.0: normal=-normal
			for vertex: int in [a,b,c]:
				if not original[vertex].is_equal_approx(points[vertex]): normals[vertex]=normal
		arrays[Mesh.ARRAY_VERTEX]=points
		arrays[Mesh.ARRAY_NORMAL]=normals
		arrays[Mesh.ARRAY_TANGENT]=null
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		result.surface_set_material(surface,source.surface_get_material(surface))
	return result

static func _clip(source: Mesh, plane: Plane) -> ArrayMesh:
	var result := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		var old := source.surface_get_arrays(surface)
		var vertices: PackedVector3Array=old[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array=old[Mesh.ARRAY_NORMAL]
		var uv := PackedVector2Array() if old[Mesh.ARRAY_TEX_UV]==null else old[Mesh.ARRAY_TEX_UV] as PackedVector2Array
		var indices: PackedInt32Array=old[Mesh.ARRAY_INDEX]
		var points := PackedVector3Array()
		var directions := PackedVector3Array()
		var texels := PackedVector2Array()
		var triangles := PackedInt32Array()
		for i in range(0,indices.size(),3):
			var polygon: Array[Dictionary]=[]
			for corner in range(3):
				var index := indices[i+corner]
				polygon.append({"p":vertices[index],"n":normals[index],"uv":uv[index] if not uv.is_empty() else Vector2.ZERO})
			var clipped: Array[Dictionary]=[]
			for edge in range(polygon.size()):
				var a: Dictionary=polygon[edge]
				var b: Dictionary=polygon[(edge+1)%polygon.size()]
				var da := plane.distance_to(a.p)
				var db := plane.distance_to(b.p)
				if da>=0.0: clipped.append(a)
				if (da>=0.0)!=(db>=0.0):
					var weight := da/(da-db)
					clipped.append({"p":(a.p as Vector3).lerp(b.p,weight),"n":(a.n as Vector3).lerp(b.n,weight).normalized(),"uv":(a.uv as Vector2).lerp(b.uv,weight)})
			for corner in range(1,clipped.size()-1):
				for vertex: Dictionary in [clipped[0],clipped[corner],clipped[corner+1]]:
					triangles.append(points.size())
					points.append(vertex.p)
					directions.append(vertex.n)
					texels.append(vertex.uv)
		if points.is_empty(): continue
		var arrays: Array=[]
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX]=points
		arrays[Mesh.ARRAY_NORMAL]=directions
		if not uv.is_empty(): arrays[Mesh.ARRAY_TEX_UV]=texels
		arrays[Mesh.ARRAY_INDEX]=triangles
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		result.surface_set_material(result.get_surface_count()-1,source.surface_get_material(surface))
	return result

static func _round_caps(source: Mesh) -> ArrayMesh:
	var result := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,source.surface_get_arrays(surface))
		result.surface_set_material(surface,source.surface_get_material(surface))
	var arrays := source.surface_get_arrays(0)
	var vertices: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
	var edges: Dictionary={}
	var positions: Dictionary={}
	for i in range(0,indices.size(),3):
		for edge in range(3):
			var a := vertices[indices[i+edge]].snapped(Vector3.ONE*0.00001)
			var b := vertices[indices[i+(edge+1)%3]].snapped(Vector3.ONE*0.00001)
			positions[a]=vertices[indices[i+edge]]
			positions[b]=vertices[indices[i+(edge+1)%3]]
			var key := [a,b] if str(a)<str(b) else [b,a]
			edges[key]=int(edges.get(key,0))+1
	var links: Dictionary={}
	for pair: Array in edges:
		if edges[pair]!=1: continue
		for side in range(2):
			if not links.has(pair[side]): links[pair[side]]=[]
			links[pair[side]].append(pair[1-side])
	var points := PackedVector3Array()
	var normals := PackedVector3Array()
	var faces := PackedInt32Array()
	while not links.is_empty():
		var start: Vector3=links.keys()[0]
		var cursor := start
		var ring := PackedVector3Array()
		while links.has(cursor):
			ring.append(positions[cursor])
			var adjacent: Array=links[cursor]
			links.erase(cursor)
			if links.has(adjacent[0]): cursor=adjacent[0]
			elif adjacent.size()>1 and links.has(adjacent[1]): cursor=adjacent[1]
			else: break
		var center := Vector3.ZERO
		for p: Vector3 in ring: center+=p
		center/=ring.size()
		var axis := (ring[0]-center).cross(ring[1]-center).normalized()
		if axis.dot(center-source.get_aabb().get_center())<0.0: axis=-axis
		var radius := ring[0].distance_to(center)
		var offset := points.size()
		for step in range(5):
			var angle := float(step)/5.0*PI*0.5
			for p: Vector3 in ring:
				var normal := (p-center).normalized()*cos(angle)+axis*sin(angle)
				points.append(center+(p-center)*cos(angle)+axis*radius*sin(angle))
				normals.append(normal)
		var tip := points.size()
		points.append(center+axis*radius)
		normals.append(axis)
		for step in range(5):
			for side in range(ring.size()):
				var a := offset+step*ring.size()+side
				var b := offset+step*ring.size()+(side+1)%ring.size()
				var c := a+ring.size() if step<4 else tip
				_triangle(faces,points,normals,a,b,c)
				if step<4: _triangle(faces,points,normals,b,offset+(step+1)*ring.size()+(side+1)%ring.size(),c)
	if points.is_empty(): return result
	var cap: Array=[]
	cap.resize(Mesh.ARRAY_MAX)
	cap[Mesh.ARRAY_VERTEX]=points
	cap[Mesh.ARRAY_NORMAL]=normals
	cap[Mesh.ARRAY_INDEX]=faces
	result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,cap)
	result.surface_set_material(result.get_surface_count()-1,source.surface_get_material(0))
	return result

static func _triangle(faces: PackedInt32Array, points: PackedVector3Array, normals: PackedVector3Array,a: int,b: int,c: int) -> void:
	if (points[c]-points[a]).cross(points[b]-points[a]).dot(normals[a]+normals[b]+normals[c])<0.0:
		faces.append_array(PackedInt32Array([a,c,b]))
	else: faces.append_array(PackedInt32Array([a,b,c]))


static func _join_wall_end(source: Mesh, end_degrees: float) -> ArrayMesh:
	var result := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		for i in range(points.size()):
			var p := points[i]
			var radius := Vector2(p.x,p.z).length()
			var distance := absf(atan2(p.z,p.x)-deg_to_rad(end_degrees))*3.18
			# Shape the existing wall's end face into the standard slender post.
			var extension := 0.026*(1.0-smoothstep(0.0,0.15,distance))*clampf((radius-3.1)/0.035,0.0,1.0)
			points[i].x*=1.0+extension/radius
			points[i].z*=1.0+extension/radius
		arrays[Mesh.ARRAY_VERTEX]=points
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		result.surface_set_material(surface,source.surface_get_material(surface))
	return result

static func _finish_light(source: Mesh, radius: float, end_degrees: float) -> ArrayMesh:
	var result := ArrayMesh.new()
	var start_angle := deg_to_rad(-27.0)
	var end_angle := deg_to_rad(end_degrees)
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		for i in range(points.size()):
			var p := points[i]
			var angle := atan2(p.z,p.x)
			var distance := minf(absf(angle-end_angle),absf(angle-start_angle))*radius
			var offset := Vector2(p.x,p.z).length()-radius
			var r := radius+offset*lerpf(0.2,1.0,smoothstep(0.012,0.12,distance))
			points[i].x=r*cos(angle)
			points[i].z=r*sin(angle)
		arrays[Mesh.ARRAY_VERTEX]=points
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		result.surface_set_material(surface,source.surface_get_material(surface))
	# Cut normal to the rail path, inside each post; never cut by world height.
	var a := end_angle+0.012/radius
	result=_clip(result,Plane(Vector3(-sin(a),0,cos(a)),0))
	a=start_angle-0.012/radius
	return _clip(result,Plane(Vector3(sin(a),0,-cos(a)),0))

static func _fit_terminal_posts(estate: Node3D) -> void:
	var meshes := estate.find_children("*","MeshInstance3D",true,false)
	for post: MeshInstance3D in meshes:
		if post.has_meta("estate_post_fitted"): continue
		var label := str(post.name)
		if not (label.begins_with("Public stair rail post") or label.begins_with("LandingTerminalPost")): continue
		var bounds := post.transform*post.get_aabb()
		if bounds.get_center().x>=0: continue
		var flight := 0
		for level in range(3):
			if absf(bounds.end.y-[5.2,8.0,10.8][level])<0.01: flight=level+1
		if flight==0: continue
		var radius := Vector2(bounds.get_center().x,bounds.get_center().z).length()
		var rail: MeshInstance3D
		for candidate: MeshInstance3D in meshes:
			var name := str(candidate.name)
			if name.begins_with("Public stair L%d handrail"%flight) and (("3_18" in name)==(radius<4.0)): rail=candidate
		if rail==null: continue
		var source := post.mesh
		var result := ArrayMesh.new()
		var local_bounds := source.get_aabb()
		var faces := rail.mesh.get_faces()
		var heights: Dictionary={}
		for surface in range(source.get_surface_count()):
			var arrays := source.surface_get_arrays(surface).duplicate(true)
			var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
			for i in range(points.size()):
				var p := points[i]
				var column := Vector2(p.x,p.z)
				if not heights.has(column):
					var origin := rail.to_local(post.to_global(Vector3(p.x,local_bounds.position.y,p.z)))
					var direction := rail.global_basis.inverse()*Vector3.UP
					var top := INF
					for face in range(0,faces.size(),3):
						var hit = Geometry3D.ray_intersects_triangle(origin,direction,faces[face],faces[face+1],faces[face+2])
						if hit!=null: top=minf(top,post.to_local(rail.to_global(hit)).y)
					heights[column]=minf(local_bounds.end.y,top+0.001)
				points[i].y=lerpf(local_bounds.position.y,float(heights[column]),(p.y-local_bounds.position.y)/local_bounds.size.y)
			arrays[Mesh.ARRAY_VERTEX]=points
			result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
			result.surface_set_material(surface,source.surface_get_material(surface))
		if not post.has_meta(COLLISION_MESH): post.set_meta(COLLISION_MESH,source)
		post.mesh=result
		post.set_meta("estate_post_fitted",true)
