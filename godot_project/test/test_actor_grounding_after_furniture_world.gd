extends "res://test/test_direct_seat_animation_restore.gd"
## Full production chair -> sleep-back -> 20 animations on the same actual actor.
const SPATIAL := preload("res://nest/spatial/estate_spatial_data.gd")
const LAYERS := preload("res://runtime/world/collision_layers.gd")

func floor_below(world: Node3D, point: Vector3, excluded: Array[RID] = []) -> Dictionary:
	# Query actual solids, never the navigation projection or invisible boundaries.
	var ray := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 0.25,
		point - Vector3.UP * 0.75, LAYERS.WORLD_SOLIDS)
	ray.exclude = excluded
	var hit := world.get_world_3d().direct_space_state.intersect_ray(ray)
	if not check(not hit.is_empty(), "No physical floor below " + str(point)): return {}
	if not check((hit["normal"] as Vector3).y > 0.7, "Support ray hit a non-walkable surface"): return {}
	return hit

func check_world_support(actor: ElfieActor, stage: String, fixture_floor_y: float) -> Dictionary:
	var position := actor.global_position
	if not check(position.is_finite(), "Nonfinite actor position: " + stage): return {}
	# This sequence stays on one bedroom floor; a lower storey is not a valid exit.
	if not check(absf(position.y-fixture_floor_y) <= 0.12,
		"Actor left bedroom floor: %s actor_y=%f fixture_floor_y=%f" % [stage,position.y,fixture_floor_y]): return {}
	var excluded: Array[RID] = [actor.get_rid()]
	var hit := floor_below(actor,position,excluded)
	if hit.is_empty(): return {}
	var floor_y := (hit["position"] as Vector3).y
	var clearance := position.y-floor_y
	print("WORLD_FLOOR_SUPPORT ",JSON.stringify({"species":actor.species_id,"stage":stage,
		"actor_y":position.y,"floor_y":floor_y,"fixture_floor_y":fixture_floor_y,
		"clearance":clearance,"feet_y":CONTACT.sole_y(actor),"collider":str(hit["collider"].get_path())}))
	if not check(absf(floor_y-fixture_floor_y) <= 0.05, "Support is not the bedroom floor: " + stage): return {}
	# Allow the production collision safe margin, not a fall or hovering body.
	if not check(clearance >= -0.02 and clearance <= 0.12, "Actor has no standing floor contact: " + stage): return {}
	return hit

func check_world_clips(actor: ElfieActor, stage: String, floor_y: float, reference: Dictionary = {}) -> Dictionary:
	var frame := actor.global_transform
	var samples := check_clips(actor,stage,reference)
	check(actor.global_transform.is_equal_approx(frame), "Animation sequence moved the physics body: " + stage)
	for pose: String in FROZEN:
		if not check(samples.has(pose), "Missing world frozen sample: " + pose): continue
		var feet_y := float(samples[pose])+frame.origin.y
		print("WORLD_FROZEN_FLOOR ",JSON.stringify({"species":actor.species_id,"stage":stage,
			"clip":pose,"feet_y":feet_y,"floor_y":floor_y,"clearance":feet_y-floor_y}))
		check(feet_y-floor_y >= -0.04 and feet_y-floor_y <= 0.10,
			"Frozen feet missed physical floor: " + actor.species_id + " " + stage + " " + pose,true)
	return samples

func run() -> void:
	Engine.time_scale = 4.0; Engine.physics_ticks_per_second = 240
	create_timer(360.0).timeout.connect(func() -> void: push_error("Furniture grounding sequence timed out"); quit(1))
	if not check(ResourceLoader.exists(SPATIAL.PATH), "Missing formal spatial resource; rebake before world test"):
		finish_report("furniture world grounding"); return
	var spatial := load(SPATIAL.PATH) as Resource
	if not check(spatial != null and spatial.matches_inputs(SPATIAL.current_inputs()),
		"Formal spatial inputs are stale; rebake before world test"):
		finish_report("furniture world grounding"); return
	var nest := (load("res://nest/nest.tscn") as PackedScene).instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	var configured := nest.apply_world_config({"nest_id":"grounding-sequence","bed_count":32,"world_revision":1})
	if not check(configured.get("accepted",false), "World configuration rejected"):
		finish_report("furniture world grounding"); return
	var physics := nest.get("_estate_physics") as Node3D
	if not check(is_instance_valid(physics) and bool(physics.get("loaded_precompiled"))
		and int(physics.get("collider_count")) > 0 and physics.get_node_or_null("StaticGeometry") != null,
		"Formal precompiled physics was not installed"):
		finish_report("furniture world grounding"); return
	if not check(nest.bake_navigation(), "No production world navigation"):
		finish_report("furniture world grounding"); return
	if not check(await nest.wait_for_navigation_sync() and nest.validate_navigation_anchors(), "World navigation not ready"):
		finish_report("furniture world grounding"); return
	await physics_frame
	await physics_frame
	var selected := OS.get_environment("ELFIENEST_GROUNDING_SPECIES")
	if not check(selected in ["", "both", "tovren", "saevi"], "Unknown grounding species"):
		finish_report("furniture world grounding"); return
	for species: String in ["tovren", "saevi"]:
		if selected not in ["", "both", species]: continue
		var chair := nest.resolve_anchor("dorm-01/chair-01")
		if not check(chair != null, "Missing chair approach"):
			finish_report("furniture world grounding"); return
		var chair_floor := floor_below(nest,chair.global_position)
		if chair_floor.is_empty():
			finish_report("furniture world grounding"); return
		var fixture_floor_y := (chair_floor["position"] as Vector3).y
		var actor := make_actor(species,chair.global_position)
		var support := check_world_support(actor,"fresh_world",fixture_floor_y)
		if support.is_empty():
			finish_report("furniture world grounding"); return
		var original: AnimationLibrary = actor.get_node("AnimationPlayer").get_animation_library("")
		var baseline := check_world_clips(actor,"fresh_world",(support["position"] as Vector3).y)
		if not check(baseline.size() == 20, "Incomplete world baseline"):
			finish_report("furniture world grounding"); return
		idle_start(actor); actor.set_process(true); actor.set_physics_process(true)
		var result := await actor.play_furniture_cycle(chair,"dorm-01/chair-01","ground-chair-"+species,"seat",nest)
		if not check(result.status == "completed", "Chair sequence failed: " + str(result)):
			finish_report("furniture world grounding"); return
		check(actor.get_node("AnimationPlayer").get_animation_library("") == original, "Chair returned before restoring library")
		actor.set_process(false); actor.set_physics_process(false)
		if check_world_support(actor,"after_chair",fixture_floor_y).is_empty():
			finish_report("furniture world grounding"); return
		print("AFTER_CHAIR_FEET ",species," actor_y=",actor.global_position.y," feet_y=",CONTACT.sole_y(actor))
		# Place at the next fixture's authored approach without configure/grounding.
		var bed := nest.resolve_anchor("dorm-01/bed-01")
		if not check(bed != null, "Missing bed approach"):
			finish_report("furniture world grounding"); return
		actor.global_position = bed.global_position; actor.velocity = Vector3.ZERO
		if check_world_support(actor,"before_sleep",fixture_floor_y).is_empty():
			finish_report("furniture world grounding"); return
		actor.set_process(true); actor.set_physics_process(true)
		result = await actor.play_furniture_cycle(bed,"dorm-01/bed-01","ground-sleep-"+species,"sleep-back",nest)
		if not check(result.status == "completed", "Sleep sequence failed: " + str(result)):
			finish_report("furniture world grounding"); return
		actor.set_process(false); actor.set_physics_process(false)
		support = check_world_support(actor,"after_sleep",fixture_floor_y)
		if support.is_empty():
			finish_report("furniture world grounding"); return
		actor.get("_animation_runtime").advance(1.0)
		check_world_clips(actor,"after_chair_then_sleep",(support["position"] as Vector3).y,baseline)
		actor.free()
		await process_frame
	nest.free()
	finish_report("actual chair -> sleep-back -> all 20 animations: original libraries and world feet")
