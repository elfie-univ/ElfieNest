extends SceneTree
## Explicit authoring entry: intermediates go to build/, not runtime startup.

const DATA := preload("res://rooms/estate/estate_spatial_data.gd")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")

func _initialize() -> void:call_deferred("run")

func require(ok: bool,message: String) -> bool:
	if not ok:push_error(message);quit(1)
	return ok

func own_children(node: Node,owner_root: Node) -> void:
	for child: Node in node.get_children():
		child.owner=owner_root
		own_children(child,owner_root)

func run() -> void:
	var started := Time.get_ticks_msec()
	var world := Node3D.new();root.add_child(world)
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	world.add_child(estate)
	var physics := PHYSICS.new();world.add_child(physics)
	physics.build(estate,true)
	if not require(physics.outdoor_access!=null,"Authoring must build real activity geometry"):return
	# Imported and generated physical bodies must be registered before baking.
	await physics_frame
	var navigation := physics.bake(world)
	if not require(navigation!=null,"Native navigation bake failed"):return
	own_children(navigation,navigation)
	var packed := PackedScene.new()
	if not require(packed.pack(navigation)==OK,"Could not pack native navigation and stair links"):return
	var data := DATA.new()
	data.collision_policy = DATA.COLLISION_POLICY
	data.source_inputs=DATA.current_inputs()
	data.navigation_settings=DATA.NAV_SETTINGS.duplicate()
	data.navigation_scene=packed
	physics.outdoor_access.capture_precompiled(data)
	data.mesh_shapes=physics._captured_mesh_shapes
	var hardscape := estate.find_child("GardenCollision_Hardscape",true,false)
	var hard_shapes := hardscape.find_children("*","CollisionShape3D",true,false)
	data.hardscape_shape=(hard_shapes[0] as CollisionShape3D).shape
	for source: String in ["GardenCollision_TreeTrunks","GardenCollision_ShoreRocks","GardenCollision_Furniture"]:
		var body := physics._static.get_node_or_null("Accessible"+source.trim_prefix("GardenCollision_"))
		if body!=null:data.accessible_shapes[source]=(body.get_child(0) as CollisionShape3D).shape
	if not require(data.matches_inputs(DATA.current_inputs()),"Generated data must satisfy runtime validation"):return
	var output := ProjectSettings.globalize_path("res://../build/estate_spatial")
	DirAccess.make_dir_recursive_absolute(output)
	var path := output.path_join("estate_spatial.res")
	if not require(ResourceSaver.save(data,path,ResourceSaver.FLAG_COMPRESS)==OK,"Could not save compiled estate resource"):return
	var reloaded := ResourceLoader.load(path,"",ResourceLoader.CACHE_MODE_IGNORE) as Resource
	if not require(reloaded!=null and reloaded.matches_inputs(DATA.current_inputs()),"Compiled resource round trip failed"):return
	var report := {"elapsed_ms":Time.get_ticks_msec()-started,"polygons":navigation.navigation_mesh.get_polygon_count(),"mesh_collider_bindings":data.mesh_shapes.size(),"boundary_segments":data.boundary_segments.size(),"movement_obstacle_groups":data.accessible_shapes.size(),"source_inputs":data.source_inputs}
	var file := FileAccess.open(output.path_join("bake-report.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"  "));file.close()
	print("ESTATE_SPATIAL_AUTHORED ",JSON.stringify(report))
	quit(0)
