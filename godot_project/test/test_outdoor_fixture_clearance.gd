extends SceneTree
const LAYOUT=preload("res://tools/outdoor_lighting_layout.gd")
func _initialize() -> void:call_deferred("run")
func run() -> void:
	create_timer(100.0,true,false,true).timeout.connect(func():quit(1))
	var published: Node3D=load("res://nest/estate/estate_outdoor_lighting.scn").instantiate()
	var published_main: Dictionary=published.get_node("Fixture_H01/Diffuser").get_meta("extras").design_lights[0]
	if float(published_main.angle)>deg_to_rad(47.0) or float(published_main.distance)>13.0:
		push_error("Waterfront beam must be fitted to the platform, not a broad path wash")
		published.free();quit(1);return
	for id: String in ["B01","B02"]:
		var fixture: Node3D=published.get_node("Fixture_"+id)
		var light: Dictionary=fixture.get_node("Diffuser").get_meta("extras").design_lights[0]
		var emitter:=Vector3(light.position[0],light.position[1],light.position[2])
		var aperture: AABB=fixture.get_node("Diffuser").mesh.get_aabb()
		if not aperture.grow(0.01).has_point(emitter):
			push_error("Approach source must remain mounted at the real diffuser: "+id)
			published.free();quit(1);return
		var target:=Vector3(light.target[0],light.target[1],light.target[2])
		if not Vector2(emitter.x-target.x,emitter.z-target.z).is_zero_approx() or target.y>=emitter.y:
			push_error("Approach fixture must cast a downward circular beam, not a tilted path wash: "+id)
			published.free();quit(1);return
		if float(light.angle)>deg_to_rad(78.0) or fixture.get_node("Diffuser").get_meta("extras").design_lights.size()!=1:
			push_error("Approach fixture must retain one bounded ring-road source: "+id)
			published.free();quit(1);return
	published.free()
	var triangles: Array[PackedVector2Array]=[PackedVector2Array([Vector2(0,0),Vector2(2,0),Vector2(0,2)])]
	assert(LAYOUT.footprint_overlaps(Vector3(0.5,0,0.5),triangles),"Fixture inside paving must be rejected")
	assert(LAYOUT.footprint_overlaps(Vector3(0.5,0,-0.1),triangles),"Fixture shield must clear the road edge too")
	assert(not LAYOUT.footprint_overlaps(Vector3(0.5,0,-0.4),triangles))
	var source=load("res://nest/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(source)
	var seat: MeshInstance3D=source.find_child("Lakeside bench seat slat",true,false)
	var old_seat_center: Vector3=(seat.global_transform*seat.get_aabb()).get_center()
	var bench_parts: Dictionary={}
	for part: MeshInstance3D in source.find_children("Lakeside*","MeshInstance3D",true,false):
		if "bench" in str(part.name) or str(part.name).begins_with("Lakeside back frame"):
			bench_parts[part]=part.global_transform
	assert(bench_parts.size()==9,"Account for seat, back, both legs and both frames")
	preload("res://nest/estate/estate_complete_final.gd")._place_lakeside_bench(source)
	var rigid_move: Transform3D=seat.global_transform*(bench_parts[seat] as Transform3D).affine_inverse()
	for part: MeshInstance3D in bench_parts:
		assert(part.global_transform.is_equal_approx(rigid_move*(bench_parts[part] as Transform3D)),"Every bench component must share the same rigid movement")
	var seat_center: Vector3=(seat.global_transform*seat.get_aabb()).get_center()
	assert(seat_center.x>old_seat_center.x+1.0,"Whole bench must move further right to clear the approach")
	assert(is_equal_approx(seat_center.y,old_seat_center.y),"Keep the seat height level")
	assert(seat.global_basis.y.normalized().is_equal_approx(Vector3.UP),"Bench must remain upright")
	var builder=LAYOUT.new()
	var result=builder.build(source)
	assert(result!=null)
	var waterfront: Node3D=result.get_node("Fixture_H01")
	if not waterfront.has_node("SingleArmHousing"):
		push_error("Waterfront platform requires the approved full-size single-arm lamp");quit(1);return
	if not (waterfront.get_node("SingleArmHousing").mesh.get_aabb().end.y>6.4 and waterfront.get_node("SingleArmHousing").mesh.get_aabb().end.y<6.7):
		push_error("Waterfront must use the plaza lamp at its full 6.5m height");result.free();source.free();quit(1);return
	assert(waterfront.position.x<seat_center.x-2.0 and waterfront.position.z<seat_center.z,"Place main lamp at the marked left end, clear of the right-hand trees")
	var daylight=preload("res://nest/estate/estate_daylight.gd")
	var platform_diffuser: MeshInstance3D=waterfront.get_node("Diffuser")
	daylight._restore_fixture_lights(platform_diffuser,{}, {})
	var actual_light: SpotLight3D=platform_diffuser.get_child(0)
	assert(actual_light.shadow_enabled and actual_light.shadow_caster_mask & daylight.LANDSCAPE_LIGHT_LAYER,"Trees must occlude the real platform source")
	platform_diffuser.remove_child(actual_light)
	actual_light.free()
	assert(not waterfront.has_node("Shield"),"Remove the old circular high lamp")
	for id in ["B01","B02"]:
		var bollard: Node3D=result.get_node("Fixture_"+id)
		assert(bollard.get_node("Housing").mesh.get_faces()==source.find_child("Outdoor R01 housing",true,false).mesh.get_faces(),"Approach lamps must reuse full-size ring-road housings")
	var left: Node3D=result.get_node("Fixture_G1")
	var right: Node3D=result.get_node("Fixture_P05")
	if not left.has_node("SingleArmHousing") or not right.has_node("SingleArmHousing"):
		push_error("Plaza pair must have continuous single-arm streetlight housings");quit(1);return
	assert(absf(left.position.x)<16.0 and left.position.z>17.0,"Move the pair inward toward the plaza edges")
	assert(left.position.is_equal_approx(Vector3(-right.position.x,right.position.y,right.position.z)),"Plaza high lamps must mirror the entrance axis")
	for fixture: Node3D in [left,right]:
		var diffuser: MeshInstance3D=fixture.get_node("Diffuser")
		var housing: MeshInstance3D=fixture.get_node("SingleArmHousing")
		assert(housing.mesh.get_aabb().end.y>6.4 and housing.mesh.get_aabb().end.y<6.7,"Plaza streetlights must reach the approved 6.5m scale")
		var light: Dictionary=diffuser.get_meta("extras").design_lights[0]
		var focus: Vector3=result.get_meta("plaza_light_focus")
		var target=fixture.position+Vector3(light.target[0],light.target[1],light.target[2])
		assert(target.is_equal_approx(focus),"Both real light axes must intersect the plaza centre")
		assert(float(light.intensity)>0.0 and float(light.intensity)<8.0*PI,"Reduce overlap energy at the shared centre")
		var emitter=fixture.position+Vector3(light.position[0],light.position[1],light.position[2])
		assert(float(light.angle)<=deg_to_rad(70.0) and float(light.distance)<=34.0,"Keep broad plaza lighting bounded")
		var axis=(target-emitter).normalized()
		for fraction in [0.35,0.65,1.0]:
			var paving=fixture.position.lerp(target,fraction)
			paving.y=target.y
			assert(axis.dot((paving-emitter).normalized())>cos(float(light.angle)),"Each beam must cover its near half, not only an isolated central spot")
		assert(not fixture.has_node("LeafShield"),"Remove the superseded pointed leaf")
		var forward=Vector3(focus.x-fixture.position.x,0,focus.z-fixture.position.z).normalized()
		var across=Vector3(-forward.z,0,forward.x)
		var along_min:=INF;var along_max:=-INF;var width:=0.0
		for vertex: Vector3 in diffuser.mesh.get_faces():
			along_min=minf(along_min,vertex.dot(forward));along_max=maxf(along_max,vertex.dot(forward))
			width=maxf(width,absf(vertex.dot(across))*2.0)
		assert(along_max-along_min>1.2 and width>0.5 and width<0.65,"Streetlight needs a readable elongated lamp head")
		assert(diffuser.mesh.get_aabb().get_center().dot(forward)>0.8,"Physical lamp head must point toward the same plaza focus")
		var down=forward*cos(deg_to_rad(65.0))-Vector3.UP*sin(deg_to_rad(65.0))
		var near:=INF;var far:=-INF
		for vertex: Vector3 in diffuser.mesh.get_faces():
			near=minf(near,vertex.dot(down));far=maxf(far,vertex.dot(down))
		assert(far-near>0.1,"Diffuser needs visible side walls, not a zero-thickness sheet")
		var arrays=housing.mesh.surface_get_arrays(0)
		var shaft_levels: Dictionary={}
		for i in range(arrays[Mesh.ARRAY_VERTEX].size()):
			var vertex: Vector3=arrays[Mesh.ARRAY_VERTEX][i]
			if vertex.y>0.2 and vertex.y<5.0:
				var level=snappedf(vertex.y,0.0001)
				if not shaft_levels.has(level):shaft_levels[level]=AABB(vertex,Vector3.ZERO)
				shaft_levels[level]=shaft_levels[level].expand(vertex)
			if vertex.y>0.2 and vertex.y<2.0:
				assert((arrays[Mesh.ARRAY_NORMAL][i] as Vector3).dot(Vector3(vertex.x,0,vertex.z))>0.0,"Housing normals must face outside")
		assert(housing.global_basis.y.normalized().is_equal_approx(Vector3.UP),"Pole world transform must be upright")
		for level in shaft_levels:
			var centre: Vector3=shaft_levels[level].get_center()
			assert(Vector2(centre.x,centre.z).length()<0.0001,"Straight shaft centre must not lean with height")
	var plaza=source.find_child(preload("res://tools/outdoor_lighting_edges.gd").PLAZA,true,false) as MeshInstance3D
	var covered:=0
	for vertex: Vector3 in plaza.mesh.get_faces():
		var ground_point=plaza.global_transform*vertex
		var lit:=false
		for fixture: Node3D in [left,right]:
			var light: Dictionary=fixture.get_node("Diffuser").get_meta("extras").design_lights[0]
			var emitter=fixture.position+Vector3(light.position[0],light.position[1],light.position[2])
			var target=fixture.position+Vector3(light.target[0],light.target[1],light.target[2])
			if emitter.distance_to(ground_point)<float(light.distance)-1.0 and (target-emitter).normalized().dot((ground_point-emitter).normalized())>cos(float(light.angle)-deg_to_rad(5.0)):lit=true
		if not lit:
			for fixture: Node3D in [left,right]:
				var light: Dictionary=fixture.get_node("Diffuser").get_meta("extras").design_lights[0]
				var emitter=fixture.position+Vector3(light.position[0],light.position[1],light.position[2])
				var target=fixture.position+Vector3(light.target[0],light.target[1],light.target[2])
				print("UNCOVERED point=",ground_point," fixture=",fixture.name," distance=",emitter.distance_to(ground_point)," angle=",rad_to_deg((target-emitter).angle_to(ground_point-emitter)))
			push_error("Every plaza vertex must sit inside a beam with angular and distance margin")
			quit(1);return
		covered+=1
	print("PLAZA_COVERAGE vertices=",covered," upright_shafts=2")

	var old=load("res://nest/estate/estate_outdoor_lighting.scn").instantiate()
	if not unchanged(waterfront,old.get_node("Fixture_H01")):
		push_error("Published waterfront lamp must match the checked single-arm geometry and light source")
		old.free()
		result.free()
		source.free()
		quit(1);return
	for fixture: Node3D in [left,right]:
		assert(fixture.position==old.get_node(NodePath(fixture.name)).position,"Keep the approved inward pole positions")
	var road=source.find_child("ROAD REF • ring continuous warm-grey stone bed",true,false)
	var trail: MeshInstance3D
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		if mesh.get_meta("extras",{}).get("forestTrail",false):trail=mesh
	var pavement=LAYOUT.paving_triangles([road,trail])
	var plaza_surfaces: Array=[road,trail]
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		if str(mesh.get_meta("extras",{}).get("landscape_ground_region","")) in ["plaza","lakeside_paving"]:plaza_surfaces.append(mesh)
	var all_paving=LAYOUT.paving_triangles(plaza_surfaces)
	for id in ["H01","B01","B02"]:
		if LAYOUT.footprint_overlaps(result.get_node("Fixture_"+id).position,all_paving,0.25):
			push_error("Lakeside lamp base overlaps paving: "+id)
			old.free();result.free();source.free();quit(1);return
	var platform=source.find_child("CY R003 circular waterfront platform closed foundation",true,false) as MeshInstance3D
	var waterfront_light: Dictionary=waterfront.get_node("Diffuser").get_meta("extras").design_lights[0]
	var waterfront_emitter=waterfront.position+Vector3(waterfront_light.position[0],waterfront_light.position[1],waterfront_light.position[2])
	var waterfront_target=waterfront.position+Vector3(waterfront_light.target[0],waterfront_light.target[1],waterfront_light.target[2])
	for vertex: Vector3 in platform.mesh.get_faces():
		var point=platform.global_transform*vertex
		if Vector2(point.x-waterfront_target.x,point.z-waterfront_target.z).length()>4.81:continue
		if waterfront_emitter.distance_to(point)>=float(waterfront_light.distance)-1.0 or (waterfront_target-waterfront_emitter).angle_to(point-waterfront_emitter)>=float(waterfront_light.angle)-deg_to_rad(3.0):
			push_error("Platform vertex outside the lamp beam margin: "+str(point))
			old.free();result.free();source.free();quit(1);return
	print("LAKESIDE_LIGHTING plaza_height=6.5 ring_approach_lamps=2 platform_coverage=pass")
	var approach_samples:=0
	var platform_faces: PackedVector3Array=platform.mesh.get_faces()
	for i in range(0,platform_faces.size(),3):
		var a: Vector3=platform.global_transform*platform_faces[i]
		var b: Vector3=platform.global_transform*platform_faces[i+1]
		var c: Vector3=platform.global_transform*platform_faces[i+2]
		if (b-a).cross(c-a).y<=0.000001:continue
		for point: Vector3 in [a,b,c,(a+b+c)/3.0]:
			if point.x>=waterfront_target.x-4.6:continue
			var approach_covered:=false
			for fixture: Node3D in [waterfront,result.get_node("Fixture_B01"),result.get_node("Fixture_B02")]:
				var source_light: Dictionary=fixture.get_node("Diffuser").get_meta("extras").design_lights[0]
				var emitter=fixture.position+Vector3(source_light.position[0],source_light.position[1],source_light.position[2])
				var target=fixture.position+Vector3(source_light.target[0],source_light.target[1],source_light.target[2])
				if emitter.distance_to(point)<float(source_light.distance)-1.0 and (target-emitter).angle_to(point-emitter)<float(source_light.angle)-deg_to_rad(3.0):approach_covered=true
			if not approach_covered:
				push_error("Approach paving lacks a real fixture beam: "+str(point))
				old.free();result.free();source.free();quit(1);return
			approach_samples+=1
	assert(approach_samples>0,"Check the real connecting path, not only the circular platform")
	print("APPROACH_LIGHT_COVERAGE samples=",approach_samples)

	for fixture: Node3D in [left,right]:
		assert(not LAYOUT.footprint_overlaps(fixture.position,all_paving,0.3),"Pole base must clear every adjoining paved path")
	for child: Node3D in old.get_children():
		var replacement=result.get_node(NodePath(child.name))
		assert(unchanged(child,replacement),"Unrelated lighting/ground changed: "+str(child.name))
	var access=preload("res://nest/estate/estate_outdoor_access.gd").new()
	root.add_child(access)
	access.load_precompiled(load("res://nest/estate/estate_spatial.res"))
	var outer_count:=0
	for fixture: Node3D in result.get_children():
		if str(fixture.name).begins_with("Fixture_O"):
			outer_count+=1
			assert(not access.contains_outdoor_point(Vector2(fixture.position.x,fixture.position.z)),"Outer lamps must stay outside approved activity areas")
			assert(not LAYOUT.footprint_overlaps(fixture.position,pavement,0.4),"Outer lamps must clear ring and junctions")
	assert(outer_count>=4,"Ring outer edge needs staggered lamps")
	var removed=[]
	for fixture: Node3D in old.get_children():
		if not str(fixture.name).begins_with("Fixture_L"):continue
		var updated=result.get_node_or_null(NodePath(fixture.name))
		if updated==null:
			assert(LAYOUT.footprint_overlaps(fixture.position,pavement))
			removed.append({"id":str(fixture.name),"point":str(fixture.position)})
		else:assert(updated.position==fixture.position,"Do not move unrelated fixtures")
	for fixture: Node3D in result.get_children():
		if str(fixture.name).begins_with("Fixture_L"):
			assert(old.has_node(NodePath(fixture.name)),"Do not add replacement fixtures")
			assert(not LAYOUT.footprint_overlaps(fixture.position,pavement))
	assert(result.get_node_or_null("Fixture_L24")==null,"Reported junction fixture must remain excluded")
	for item: Dictionary in removed:assert(item.id=="Fixture_L24","Do not remove unrelated fixtures")
	var before=ground_buffers(old);var after=ground_buffers(result)
	assert(before==after,"Road and lawn geometry must remain exact")
	own(result,result)
	var packed=PackedScene.new();assert(packed.pack(result)==OK)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://../build/asset_design/road-fixtures"))
	assert(ResourceSaver.save(packed,"res://../build/asset_design/road-fixtures/estate_outdoor_lighting.scn",ResourceSaver.FLAG_COMPRESS)==OK)
	var file=FileAccess.open("res://../build/asset_design/road-fixtures/fixtures.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"removed":removed,"ground_patches":before.size()},"  "))
	print("PASS fixture clearance; removed=",JSON.stringify(removed)," unchanged_ground_patches=",before.size())
	old.free();quit()
func unchanged(a: Node3D,b: Node3D) -> bool:
	if a.transform!=b.transform or a.get_child_count()!=b.get_child_count():return false
	if a is MeshInstance3D:
		if a.mesh.get_faces()!=b.mesh.get_faces():return false
	for key in a.get_meta_list():
		if a.get_meta(key)!=b.get_meta(key):return false
	for i in range(a.get_child_count()):
		if not unchanged(a.get_child(i),b.get_child(i)):return false
	return true
func own(node: Node,top: Node) -> void:
	for child in node.get_children():child.owner=top;own(child,top)
func ground_buffers(root_node: Node) -> Dictionary:
	var result={}
	for mesh: MeshInstance3D in root_node.find_children("*","MeshInstance3D",true,false):
		if not mesh.has_meta("source_ground"):continue
		var signature=[]
		for surface: Dictionary in mesh.mesh.get("_surfaces"):
			var data={}
			for key in ["vertex_data","attribute_data","index_data","format","vertex_count","index_count","aabb","uv_scale"]:
				if surface.has(key):data[key]=surface[key]
			signature.append(data)
		var key=str(mesh.get_meta("source_ground"))+"/"+str(mesh.get_meta("source_surface"))+"/"+str(hash(mesh.get_meta("source_indices")))
		result[key]=signature
	return result
