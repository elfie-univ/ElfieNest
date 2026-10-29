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
	var old=load("res://rooms/estate/estate_outdoor_lighting.scn").instantiate()
	var road=source.find_child("ROAD REF • ring continuous warm-grey stone bed",true,false)
	var trail: MeshInstance3D
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		if mesh.get_meta("extras",{}).get("forestTrail",false):trail=mesh
	var pavement=LAYOUT.paving_triangles([road,trail])
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
