extends SceneTree

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	if not require(ResourceLoader.exists("res://runtime/lab/estate_animation_picker.gd"), "Missing direct animation dropdown player"): return
	var catalog := load("res://runtime/lab/estate_animation_picker_catalog.gd") as GDScript
	var entries: Array = catalog.entries()
	if not require(entries.size()==9,"Main menu must contain nine functional groups, without duplicate clip groups"): return
	if not require(grouped_catalog(catalog),"Grouped selections must preserve the original scenarios and all source motions"): return
	var ids := {}
	for entry: Dictionary in entries:
		if not require(not ids.has(entry["id"]),"Duplicate menu item"): return
		ids[entry["id"]]=true
	if not require(catalog.uses_picker("?mode=animation_journey&autoplay=1") and not catalog.uses_picker("?mode=animation_journey&playback=continuous") and not catalog.uses_picker("?observer=product"),"Picker must be explicit and preserve continuous/product modes"): return
	var host_script := load("res://runtime/lab/estate_animation_picker.gd") as GDScript
	if not require(host_script!=null,"Picker UI must compile"): return
	if OS.get_environment("ELFIENEST_PICKER_CASE")=="catalog":
		print("PASS grouped catalog: nine functions, original variants, 25 source clips and explicit head gestures")
		quit(0)
		return
	if OS.get_environment("ELFIENEST_PICKER_CASE")=="clips":
		if clip_inventory(): quit(0)
		return
	if OS.get_environment("ELFIENEST_PICKER_CASE")=="samples":
		if await samples(): quit(0)
		return
	var host := host_script.new() as Control
	root.add_child(host)
	if not require(host.choices.item_count==9 and host.source_choices.item_count==28,"UI must separate nine functions from 25 clips and two gestures"): return
	# Several choices in the same frame must create only the final requested
	# fixture. Switching while playback awaits a frame must free the old owner.
	host.select_source_animation(0)
	host.select_source_animation(1)
	await process_frame
	await process_frame
	var old: Node3D=host.runner
	if not require(is_instance_valid(old) and old.entry["id"]=="clip:walking","Latest selected animation must play directly"): return
	for frame in range(240):
		await process_frame
		if old.get("_actor")!=null: break
	if not require(old.get("_actor")!=null,"Selected clip actor did not load"): return
	await physics_frame
	await process_frame
	var actor: ElfieActor=old.get("_actor")
	var shape: CollisionShape3D=actor.get_node("CollisionShape3D")
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape=shape.shape
	query.transform=shape.global_transform
	query.exclude=[actor.get_rid()]
	query.collision_mask=actor.collision_mask
	if not require(actor.get_world_3d().direct_space_state.intersect_shape(query,1).is_empty(),"Direct clip fixture starts inside furniture"): return
	host.toggle_pause()
	if not require(old.process_mode==Node.PROCESS_MODE_DISABLED,"Pause must suspend the selected fixture"): return
	if not require(host.preview.render_target_update_mode==SubViewport.UPDATE_DISABLED,"Pause must freeze the rendered water/shader image too"): return
	host.select_animation(8) # Water, without passing any door or stair chapter.
	host.select_variant(2) # Lake.
	host.select_water_time(1) # The same lake at night.
	await process_frame
	await process_frame
	if not require(not is_instance_valid(old) and host.preview.get_child_count()==1,"Switch must cancel and destroy the previous actor/coroutine"): return
	for frame in range(240):
		await process_frame
		if host.runner.get("_water")!=null: break
	if not require(host.runner.entry["id"]=="lake" and host.runner.get("_water")!=null,"Lake selection must show the original water immediately"): return
	if not require(bool(host.runner.entry["night"]),"Water time selector must reach the selected lake, not switch back to the fountain"): return
	if not require(host.runner.plan.completed.is_empty(),"Single preview must never certify skipped journey chapters"): return
	old=host.runner
	host.replay_selected()
	await process_frame
	await process_frame
	if not require(not is_instance_valid(old) and host.runner.entry["id"]=="lake" and bool(host.runner.entry["night"]),"Replay must retain the chosen water scene and time"): return
	host.select_source_animation(1) # Replay from an independently clean fixture.
	await process_frame
	await process_frame
	if not require(host.preview.get_child_count()==1 and host.runner.entry["id"]=="clip:walking","Replay must keep only one fixture"): return
	host.select_source_animation(26)
	await process_frame
	await process_frame
	for frame in range(240):
		await physics_frame
		await process_frame
		if host.runner.completed: break
	if not require(host.runner.entry["id"]=="motion:shake_head" and host.runner.completed and str(host.runner.get("_last_error")).is_empty(),"Explicit head gesture must play and finish through the existing actor runtime"): return
	host.queue_free()
	await process_frame
	await physics_frame
	if OS.get_environment("ELFIENEST_PICKER_CASE")!="selection":
		if not clip_inventory(): return
		if not await samples(): return
	print("PASS animation picker: complete menu, latest selection wins, direct clip/water, pause, cancellation, replay and no fabricated journey progress")
	quit(0)

func grouped_catalog(catalog: GDScript) -> bool:
	var ids: Array[String] = []
	for entry: Dictionary in catalog.entries(): ids.append(entry["id"])
	if not require(ids==["arrival","stairs","doors","garden-door","chair","sofa","sleep","embodiment","water"],"Functional groups must preserve arrival, both door types and embodiment without duplicate locomotion/inventory groups"): return false
	for pair: Array in [["sofa",["sofa-central","sofa-cinema","sofa-tea"]],["sleep",["sleep-back","sleep-left","sleep-right"]],["water",["fountain","spillway","lake"]]]:
		for index in range(pair[1].size()):
			var selected: Dictionary=catalog.resolve_entry(pair[0],index,true)
			if not require(selected["id"]==pair[1][index],"Variant must keep its original scenario: "+str(pair[1][index])): return false
			if pair[0]=="water" and not require(bool(selected["night"]),"All water scenes must support night playback"): return false
	var clips := {}
	var gestures := {}
	for entry: Dictionary in catalog.source_entries():
		if entry["kind"]=="clip": clips[entry["clip"]]=true
		else: gestures[entry["motion"]]=true
	if not require(clips.size()==25 and gestures.has("nod_head") and gestures.has("shake_head"),"Keep every source clip and expose both procedural head gestures"): return false
	for key: String in preload("res://runtime/lab/estate_animation_journey_plan.gd").clip_sources():
		if not require(clips.has(key),"Lost independently playable source clip: "+key): return false
	return true

func clip_inventory() -> bool:
	var factory := preload("res://runtime/lab/chair_world_review.gd").new()
	var actor: ElfieActor=factory.create_actor()
	factory.free()
	root.add_child(actor)
	actor.set_process(false)
	actor.set_physics_process(false)
	var clips: Dictionary=preload("res://runtime/lab/estate_animation_journey_plan.gd").clip_sources()
	for key: String in clips:
		var source := load(clips[key]) as AnimationLibrary
		var clip := preload("res://runtime/actor/chair_clip_sequence.gd")._retarget(source,actor,true)
		if not require(clip!=null and clip.get_track_count()>0,"Individual clip is not ready for this species: "+key): return false
	actor.free()
	print("PASS all 25 selectable source clips have imported rest metadata and valid target-rig tracks")
	return true

func samples() -> bool:
	var script := load("res://runtime/lab/estate_animation_picker_runner.gd") as GDScript
	var catalog := load("res://runtime/lab/estate_animation_picker_catalog.gd") as GDScript
	Engine.time_scale=4.0
	for id: String in ["doors","garden-door","arrival","sleep-left","chair","sofa-central","sofa-cinema","sofa-tea"]:
		var only := OS.get_environment("ELFIENEST_PICKER_SAMPLE")
		if not only.is_empty() and only!=id: continue
		var entry: Dictionary=catalog.entry_for(id)
		var viewport := SubViewport.new()
		viewport.own_world_3d=true
		root.add_child(viewport)
		var runner: Node3D=script.new()
		viewport.add_child(runner)
		runner.start(entry)
		var ready := false
		for frame in range(1200):
			await physics_frame
			await process_frame
			if runner.completed:
				if not require(str(runner.get("_last_error")).is_empty(),"Selected sample failed: %s / %s" % [id,runner.get("_last_error")]): return false
				ready=true
				break
			var actor: Node3D=runner.get("_actor")
			if (id.begins_with("sleep-") and runner.get("sleep_sample")!=null) or (id=="chair" or id.begins_with("sofa-")) and actor!=null and bool(actor.get("root_motion")):
				ready=true
				break
		if not require(ready,"Sample did not prepare directly: "+id): return false
		print("PASS picker prepared original sample: ",id," phase=",runner.get("_phase"))
		viewport.free()
		await process_frame
		await physics_frame
	Engine.time_scale=1.0
	return true
