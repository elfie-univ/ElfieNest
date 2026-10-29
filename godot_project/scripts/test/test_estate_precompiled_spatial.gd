extends SceneTree

const DATA := preload("res://rooms/estate/estate_spatial_data.gd")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")

func _initialize() -> void:call_deferred("run")

func require(ok: bool,message: String) -> bool:
	if not ok:push_error(message);quit(1)
	return ok

func run() -> void:
	if not require(ResourceLoader.exists(DATA.PATH),"Missing offline estate spatial resource"):return
	var data := load(DATA.PATH) as Resource
	var inputs := DATA.current_inputs()
	if not require(data.matches_inputs(inputs),"Compiled estate resource must match current model and actor clearance"):return
	var old_collision: Resource = data.duplicate()
	old_collision.format_version = 2
	if not require(not old_collision.matches_inputs(inputs),"Pre-TV collision cache must require rebaking"):return
	var unspecified_policy: Resource = data.duplicate()
	unspecified_policy.collision_policy = ""
	if not require(not unspecified_policy.matches_inputs(inputs),"Legacy resource defaults must not silently adopt a new collision policy"):return
	var stale: Resource=data.duplicate()
	stale.source_inputs={"scene":"changed","instances":"changed"}
	if not require(not stale.matches_inputs(inputs),"Stale resources must be rejected"):return
	var wrong_actor: Resource=data.duplicate()
	wrong_actor.navigation_settings=data.navigation_settings.duplicate()
	wrong_actor.navigation_settings["agent_radius"]=0.5
	if not require(not wrong_actor.matches_inputs(inputs),"Changed actor clearance must require rebaking"):return
	var world := Node3D.new();root.add_child(world)
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	world.add_child(estate)
	var physics := PHYSICS.new();world.add_child(physics)
	physics.build(estate)
	if not require(physics.loaded_precompiled,"Normal startup must load spatial data"):return
	if not require(physics.outdoor_access.loaded_precompiled,"Activity masks and boundaries must load without calculation"):return
	var region := physics.bake(world)
	if not require(region!=null and region.navigation_mesh.get_polygon_count()>1000,"Loaded native navigation must contain the actual estate"):return
	if not require(region.find_children("*","NavigationLink3D",true,false).size()>0,"Precomputed navigation must preserve stair links"):return
	if not await tv_detour(world): return
	print("PASS precompiled estate: input invalidation, actor clearance, cached collision shapes/activity and native navigation with stair links")
	quit(0)


func tv_detour(world: Node3D) -> bool:
	var map := world.get_world_3d().navigation_map
	var start := Vector3.ZERO
	var target := Vector3.ZERO
	var path := PackedVector3Array()
	for frame in range(120):
		await physics_frame
		await process_frame
		start = NavigationServer3D.map_get_closest_point(map, Vector3(-5.2, 0.38, 0.7))
		target = NavigationServer3D.map_get_closest_point(map, Vector3(-3.3, 0.38, 0.7))
		path = NavigationServer3D.map_get_path(map, start, target, true)
		if start.distance_to(Vector3(-5.2, 0.38, 0.7)) < 0.3 and target.distance_to(Vector3(-3.3, 0.38, 0.7)) < 0.3 and path.size() > 1: break
	print("TV_DETOUR_INPUTS start=", start, " target=", target, " path=",path)
	if not require(path.size() > 2, "TV route must detour instead of crossing its newly compiled solid"): return false
	var cabinet := AABB(Vector3(-4.54, 0.36, -0.555), Vector3(0.58, 0.54, 2.55))
	for index in range(1, path.size()):
		if not require(absf(path[index].y-0.38) < 0.16 and not cabinet.grow(0.2).intersects_segment(path[index-1], path[index]), "Compiled route crosses the TV or climbs onto furniture"): return false
	var factory := preload("res://runtime/lab/chair_world_review.gd").new()
	var actor: ElfieActor = factory.create_actor()
	factory.free()
	world.add_child(actor)
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	player.add_animation_library("", preload("res://runtime/actor/chair_clip_sequence.gd").locomotion_for(actor))
	actor.configure("physical-tv-detour", start)
	await physics_frame
	await process_frame
	Engine.time_scale = 4.0
	if not require(actor.move_to("walk-around-original-tv", target, 20.0), "TV detour did not start"): return false
	var result: Array = await actor.navigation_terminal
	Engine.time_scale = 1.0
	if not require(str(result[1]) == "completed", "TV detour was physically blocked: " + str(result)): return false
	print("PASS actual estate TV detour: ", start, " -> ", actor.global_position, " path=", path)
	return true
