extends SceneTree
func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	create_timer(85.0, true, false, true).timeout.connect(func(): quit(1))
	var script=load("res://runtime/lab/estate_navigation_tour.gd")
	assert(script!=null)
	var tour=script.new()
	root.add_child(tour)
	tour.actor=CharacterBody3D.new()
	tour.add_child(tour.actor)
	tour.route=[{"title":"first","point":Vector3.ZERO},{"title":"second","point":Vector3.ONE}]
	tour.index=0
	tour.accept_terminal("leg-0","failed","movement_blocked")
	assert(tour.index==0 and not tour.blocked.is_empty(),"A failed route must stop without advancing")
	tour.blocked=""
	tour.accept_terminal("old-command","completed","")
	assert(tour.index==0,"Stale completion must not advance")
	tour.accept_terminal("leg-0","completed","")
	assert(tour.index==1,"Successful physical arrival advances exactly once")
	tour.accept_terminal("leg-0","completed","")
	assert(tour.index==1)
	tour.set_speed(4)
	assert(Engine.physics_ticks_per_second==240 and Engine.time_scale==4.0)
	tour.adjust_for_framerate(12.0, 1.0)
	assert(tour.effective_speed==4, "One slow sample must not switch speed")
	tour.adjust_for_framerate(12.0, 1.0)
	assert(tour.speed==4 and tour.effective_speed==1)
	assert(Engine.physics_ticks_per_second==60 and Engine.time_scale==1.0)
	tour.adjust_for_framerate(60.0, 5.0)
	assert(tour.effective_speed==1, "Recovery needs sustained headroom")
	tour.adjust_for_framerate(60.0, 5.0)
	assert(tour.effective_speed==2)
	tour.adjust_for_framerate(60.0, 10.0)
	assert(tour.effective_speed==4)
	tour.set_speed(1)
	tour.adjust_for_framerate(60.0, 20.0)
	assert(tour.effective_speed==1, "Never exceed the requested speed")
	tour.free()
	assert(Engine.time_scale==1.0 and Engine.physics_ticks_per_second==60)
	print("PASS navigation tour: stop, stale terminal, single advance, fixed physical timestep")
	if OS.get_environment("TOUR_UNIT_ONLY")=="1":
		quit();return
	var nest=load("res://rooms/nest.tscn").instantiate()
	root.add_child(nest)
	var characters=Node3D.new();root.add_child(characters)
	var real_tour=script.new();root.add_child(real_tour)
	await real_tour.setup(nest,characters)
	if not real_tour.world_ready:
		print("TOUR SETUP FAILED ",real_tour.blocked);quit(1);return
	var invalid=0
	for stage in real_tour.route:
		if not stage.point.is_finite() or not str(stage.get("invalid", "")).is_empty():
			print("INVALID TOUR STOP ",stage);invalid+=1
	print("TOUR READY stops=",real_tour.route.size()," invalid=",invalid)
	real_tour.pause_each=true
	real_tour.start_or_continue()
	while real_tour.running:
		await physics_frame
	print("TOUR FIRST LEG ",real_tour.history)
	var passed=real_tour.index==1 and invalid==0
	real_tour.free()
	quit(0 if passed else 1)
