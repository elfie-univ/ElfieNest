extends SceneTree
const LAYOUT=preload("res://scripts/tools/outdoor_lighting_layout.gd")
func _initialize() -> void:call_deferred("run")
func run() -> void:
	create_timer(100.0,true,false,true).timeout.connect(func():quit(1))
	var triangles: Array[PackedVector2Array]=[PackedVector2Array([Vector2(0,0),Vector2(2,0),Vector2(0,2)])]
	assert(LAYOUT.footprint_overlaps(Vector3(0.5,0,0.5),triangles),"Fixture inside paving must be rejected")
	assert(LAYOUT.footprint_overlaps(Vector3(0.5,0,-0.1),triangles),"Fixture shield must clear the road edge too")
	assert(not LAYOUT.footprint_overlaps(Vector3(0.5,0,-0.4),triangles))
	var source=load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(source)
	var builder=LAYOUT.new()
	var result=builder.build(source)
	assert(result!=null)
	var left: Node3D=result.get_node("Fixture_G1")
	var right: Node3D=result.get_node("Fixture_P05")
	if absf(left.position.x)<16.0 or left.position.z<16.0:
		push_error("Plaza lamps must sit outside the ring at the paired front corners");quit(1);return
	assert(left.position.is_equal_approx(Vector3(-right.position.x,right.position.y,right.position.z)),"Plaza high lamps must mirror the entrance axis")
	for fixture: Node3D in [left,right]:
		var diffuser: MeshInstance3D=fixture.get_node("Diffuser")
		var light: Dictionary=diffuser.get_meta("extras").design_lights[0]
		assert(float(light.intensity)>=8.0*PI and float(light.target[0])*fixture.position.x<0,"High lamps must illuminate toward plaza")
		assert(diffuser.mesh.get_aabb().size.x>fixture.get_node("Shield").mesh.get_aabb().size.x,"Luminous lip must remain visible around cap")
		assert(diffuser.mesh.get_aabb().size.x>=0.65,"High lamps need a broad luminous underside")
		assert(diffuser.mesh.get_aabb().size.y>=0.08,"Diffuser must be readable from the side")

	var old=load("res://rooms/estate/estate_outdoor_lighting.scn").instantiate()
	var road=source.find_child("ROAD REF • ring continuous warm-grey stone bed",true,false)
	var trail: MeshInstance3D
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		if mesh.get_meta("extras",{}).get("forestTrail",false):trail=mesh
	var pavement=LAYOUT.paving_triangles([road,trail])
	var access=preload("res://rooms/estate/estate_outdoor_access.gd").new()
	root.add_child(access)
	access.load_precompiled(load("res://rooms/estate/estate_spatial.res"))
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
	assert(ResourceSaver.save(packed,"res://../build/asset_design/road-fixtures/estate_outdoor_lighting.scn",ResourceSaver.FLAG_COMPRESS)==OK)
	var file=FileAccess.open("res://../build/asset_design/road-fixtures/fixtures.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"removed":removed,"ground_patches":before.size()},"  "))
	print("PASS fixture clearance; removed=",JSON.stringify(removed)," unchanged_ground_patches=",before.size())
	old.free();quit()
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
