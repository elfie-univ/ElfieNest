extends "res://runtime/lab/estate_animation_journey.gd"
## One disposable local audition. Never advances or certifies a journey plan.
signal finished(success: bool, reason: String)
var entry: Dictionary
var fixture: Node3D
var completed := false
var sleep_sample: Node3D
var confirmed_arrival: Node3D
signal picker_frame
signal picker_physics_frame

func _process(delta: float) -> void:
	if sleep_sample == null: super(delta)
	picker_frame.emit()

func _physics_process(delta: float) -> void:
	super(delta)
	picker_physics_frame.emit()

func wait_preview_delay(seconds: float) -> void:
	await _wait(seconds)

func _wait(seconds: float, sample: Callable = Callable()) -> void:
	var elapsed := 0.0
	while elapsed<seconds:
		# This signal belongs to the disposable runner, not the global tree.
		# Freeing it cancels waits rather than waking an obsolete scene later.
		await picker_frame
		if _paused: continue
		elapsed=minf(elapsed+get_process_delta_time(),seconds)
		if sample.is_valid(): sample.call(elapsed)

func run_chair_trial() -> void:
	_swivel.set("review_clock",self)
	await super.run_chair_trial()

func _walk(id: String, target: Vector3) -> bool:
	if _actor.global_position.distance_to(target)<0.1: return true
	return await super._walk(id,target)

func start(value: Dictionary) -> void:
	entry = value
	review_clock=self
	_phase = "准备所选场景…"
	if entry["id"]=="arrival":
		await _play_confirmed_arrival()
		return
	fixture = preload("res://runtime/lab/estate_animation_picker_fixture.gd").new()
	add_child(fixture)
	var error: String = await fixture.build(str(entry["id"]))
	if not error.is_empty(): _finish(false, error); return
	_nest = fixture
	_geometry = fixture.geometry
	_tour_world = preload("res://runtime/lab/estate_tour_room.gd").new()
	add_child(_tour_world)
	_tour_world.geometry = _geometry
	_tour_world.physics = fixture._estate_physics
	_tour_world.semantics = fixture._estate_semantics
	_actor = create_actor()
	add_child(_actor)
	_player = _actor.get_node("AnimationPlayer") as AnimationPlayer
	_player.add_animation_library("", CLIPS.locomotion_for(_actor))
	if str(entry["id"])=="chair" or str(entry["id"]).begins_with("sofa-"):
		_player.add_animation_library("chair", _library(_actor))
	_actor.configure("local-animation-picker", _spawn_point())
	_camera = Camera3D.new()
	add_child(_camera)
	_camera.near = 0.03
	_camera.fov = 58
	_camera.make_current()
	_focus = _actor.global_position + Vector3.UP * 0.7
	_camera.global_position = _focus + _follow_offset
	_camera.look_at(_focus)
	_ready_camera = true
	_phase = "播放所选动画"
	var success := await _play_entry()
	_finish(success, _last_error)

func _play_confirmed_arrival() -> void:
	# Reuse the accepted presentation intact, including its own actor/locomotion.
	# Do not create a chair actor at ground level or hand this view to tour follow.
	_camera=Camera3D.new()
	add_child(_camera)
	_camera.near=0.03
	_camera.make_current()
	confirmed_arrival=preload("res://runtime/lab/estate_event_review.gd").new()
	confirmed_arrival.set("camera_owner",self)
	add_child(confirmed_arrival)
	confirmed_arrival.set_process(false)
	confirmed_arrival.call("apply_arrival_night")
	_arrival=confirmed_arrival.get("platform_cycle")
	if _arrival==null:
		_finish(false,"Original arrival presentation is missing")
		return
	_actor=_arrival.get_node("LocalPlatformBody")
	_player=_actor.get_node("AnimationPlayer")
	_phase="播放所选动画"
	# One complete accepted arrival, walk down, then remain visible. No reset.
	await _wait(ARRIVAL_TIMING.REVIEW_END,Callable(_arrival,"sample"))
	_finish(true,"")

func configure_estate_event_review(views: Array[Dictionary]) -> void:
	for view: Dictionary in views:
		if view["id"]!="C04-arrival": continue
		_camera.global_position=view["camera"]
		_camera.fov=view["fov"]
		_camera.look_at(view["target"])
	_ready_camera=false

func select_observer_camera_by_id(_id: String) -> void:
	# The dropdown owns selection; the original URL's default bed view cannot
	# replace the fixed arrival front camera configured above.
	pass

func observer_camera_catalog() -> Dictionary:
	return {"active_id":"C04-arrival"}

func observer_presentation_paused() -> bool:
	return _paused

func _finish(success: bool, reason: String) -> void:
	completed = true
	_phase = "播放完毕，可重播或选择其他动画" if success else "已停止："+reason
	finished.emit(success, reason)
	print("ANIMATION_PICKER ", JSON.stringify({"id":entry.get("id"),"played":success,"reason":reason,"journey_accepted":false}))

func _spawn_point() -> Vector3:
	var id := str(entry["id"])
	var anchor := "dorm-01/bed-01" if id=="chair" or id.begins_with("sleep-") or id=="embodiment" else "central-01/activity"
	if id=="stairs": anchor="central-02/activity"
	var marker := fixture.resolve_anchor(anchor) as Marker3D
	var point := marker.global_position if marker != null else Vector3(0, 0.32, 0)
	# The raw-clip audience needs a full-body view ahead of the lounge tables.
	if entry["kind"]=="clip" or id in ["locomotion","expressions","clip-inventory"]: point.z+=3.0
	return point

func _play_entry() -> bool:
	var id := str(entry["id"])
	if entry["kind"]=="clip": return await _preview_clips([entry["clip"]])
	if entry["kind"]=="gesture":
		_phase = str(entry["title"])
		if not _actor.play_preview_intent({"type":"motion", "motion":entry["motion"]}): return _fail("Missing gesture: "+str(entry["motion"]))
		await _wait(1.5)
		return true
	match id:
		"arrival", "platform-exit":
			if not _bind_arrival(): return false
			if id=="platform-exit": _arrival.sample(ARRIVAL_TIMING.ARRIVAL_END)
			return await _execute_chapter(id)
		"stairs": return await _walk_anchor("central-01/activity")
		"doors", "garden-door": return await _door_sample(id)
		"locomotion": return await _preview_clips(["idle","walking","running","left_turn","right_turn","left_turn_90","right_turn_90","left_strafe","right_strafe","left_strafe_walking","right_strafe_walking"])
		"expressions":
			if not await _preview_clips(["jump","twist_dance","pose_waving","pose_thinking","pose_victory","pose_thumbs_up","pose_hands_on_hips"]): return false
			for motion: String in ["nod_head","shake_head"]:
				_phase = motion
				if not _actor.play_preview_intent({"type":"motion","motion":motion}): return _fail("Missing gesture: "+motion)
				await _wait(1.5)
			return true
		"chair": return await _desk_chair()
		"sofa-central", "sofa-cinema", "sofa-tea":
			if not _tour_world.bind_seats() or not await _measure_motion(): return _fail("Original sofa contact unavailable")
			var index := ["sofa-central","sofa-cinema","sofa-tea"].find(id)
			var seat: Dictionary = _tour_world.seats[index]
			var approach: Transform3D = PLAN.approach(seat["contact"],_measured_motion)
			var spawn := approach.origin - approach.basis.z * 0.4
			spawn.y = float(seat["floor_y"])+0.02
			_actor.configure("local-sofa-picker", spawn)
			return await _visit_seat(index) or _fail(_phase)
		"sleep-back", "sleep-left", "sleep-right", "embodiment": return await _sleep_sample(id)
		"fountain", "spillway", "lake", "water-night": return await _water_sample(id)
		"clip-inventory": return await _preview_clips(JOURNEY_PLAN.clip_sources().keys())
	return _fail("Unknown animation: "+id)

func _sleep_sample(id: String) -> bool:
	var duvet: MeshInstance3D
	for mesh: MeshInstance3D in _geometry.find_children("*","MeshInstance3D",true,false):
		var extra := mesh.get_meta("extras",{}) as Dictionary
		if extra.get("module")=="M01" and extra.get("resident")=="A" and extra.get("piece")=="bed_cover": duvet=mesh
	var prepared := preload("res://runtime/lab/estate_sleep_journey.gd").new()
	add_child(prepared)
	var error: String=prepared.prepare(_actor,fixture.resolve_anchor("dorm-01/bed-01"),duvet,_geometry,fixture._estate_physics,"dorm-01/bed-01")
	if not error.is_empty(): return _fail(error)
	# The approved standalone controller already owns a correctly posed local
	# body. Show that fixture directly; no travelling actor/contact handoff.
	_actor.free()
	_actor=prepared.probe
	_actor.visible=true
	sleep_sample=prepared.review
	var target := (duvet.global_transform*duvet.get_aabb()).get_center()+Vector3.UP*0.3
	_camera.global_position=target+Vector3(2.2,1.7,2.4)
	_camera.look_at(target)
	_ready_camera=false
	sleep_sample.set_mode("side-left" if id=="sleep-left" else ("side-right" if id=="sleep-right" else "back"))
	if id=="embodiment":
		sleep_sample.sample_bedding(7.0)
		await _wait(6.0,Callable(prepared.effects,"preview_cover"))
	else:
		sleep_sample.sample_bedding(0.0)
		await _wait(sleep_sample.CYCLE,func(seconds: float) -> void:
			# Hold the restored bed at the end instead of wrapping to approach.
			sleep_sample.sample_bedding(minf(seconds, sleep_sample.CYCLE-0.001))
			_phase="原床睡眠 / "+str(sleep_sample.animation_stage))
	return true

func _preview_clips(keys: Array) -> bool:
	_actor.set("audition",true)
	var library := AnimationLibrary.new()
	_player.add_animation_library("picker",library)
	for key: String in keys:
		var source := load(JOURNEY_PLAN.clip_sources()[key]) as AnimationLibrary
		var clip := CLIPS._retarget(source,_actor,true)
		if clip==null: return _fail("Source clip cannot retarget: "+key)
		clip.loop_mode = Animation.LOOP_NONE
		library.add_animation(key,clip)
		_phase = "单独动作："+key
		_player.play("picker/"+key,0.15)
		await _wait(maxf(1.2,clip.length))
	_player.pause()
	return true

func _door_sample(id: String) -> bool:
	var wanted: Array[Dictionary] = []
	for door: Dictionary in fixture._estate_physics._doors:
		var mesh := door["mesh"] as Node3D
		var garden := bool(mesh.get_meta("generated_garden_leaf",false))
		var connection := str((mesh.get_meta("extras",{}) as Dictionary).get("connection",""))
		if (id=="garden-door" and garden) or (id=="doors" and connection=="M01"): wanted.append(door)
	if wanted.size()!=(2 if id=="garden-door" else 1): return _fail("Original door leaves are missing")
	_actor.visible = false
	_actor.set_physics_process(false)
	fixture._estate_physics.set_physics_process(false)
	var center := Vector3.ZERO
	var controls: Array[RefCounted] = []
	for door: Dictionary in wanted:
		center += door["center"] as Vector3
		controls.append(preload("res://rooms/estate/estate_door.gd").new(door))
	center /= wanted.size()
	_actor.global_position = center - Vector3.UP*1.2
	_camera.global_position = center + (Vector3(3,1.4,4) if id=="doors" else Vector3(0,1.5,5))
	_camera.look_at(center)
	_ready_camera=false
	var previous: Array[float] = [0.0]
	await _wait(6.5,func(seconds: float) -> void:
		var delta := seconds - previous[0]
		previous[0] = seconds
		var nearby: Array[Node3D] = []
		if seconds<2.5: nearby.append(_actor)
		for control: RefCounted in controls: control.advance(delta,false,nearby)
		_phase = "门扇打开 → 保持 → 延迟关闭")
	return true

func _water_sample(id: String) -> bool:
	_actor.visible=false
	_actor.set_physics_process(false)
	var wanted := "Reference fountain water" if id in ["fountain","water-night"] else ("COMPLETE Inset natural lake receiving under spillway" if id=="spillway" else "COMPLETE Inset natural lake")
	var mesh := _mesh("",wanted)
	if mesh==null: return _fail("Original water surface missing")
	var target := (mesh.global_transform*mesh.get_aabb()).get_center()
	_camera.global_position=target+Vector3(4,3,5)
	_camera.look_at(target)
	_ready_camera=false
	_water=preload("res://rooms/estate/estate_water_display.gd").new()
	add_child(_water)
	_water.bind(_geometry,(fixture.get_node("WorldEnvironment") as WorldEnvironment).environment,true)
	_water.set_process(false)
	_splash=preload("res://runtime/lab/estate_fountain_splash.gd").new()
	add_child(_splash)
	_splash.bind(_geometry)
	await _wait(12.0,func(seconds: float) -> void:
		_water.sample(seconds,bool(entry.get("night",id=="water-night")))
		_splash.sample(seconds))
	return true
