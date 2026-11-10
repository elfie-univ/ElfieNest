extends SceneTree
const NEST := preload("res://nest/nest.tscn")
var nest: ModularNest

func _initialize() -> void: call_deferred("run")
func default_cases() -> String: return "chair,chair-d,sleep-back"
func require(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok

func run() -> void:
	# Four times wall-clock speed, retaining the production 1/60 s physics step.
	Engine.time_scale = 4.0
	Engine.physics_ticks_per_second = 240
	create_timer(300.0).timeout.connect(func() -> void: push_error("Furniture world check timed out"); quit(1))
	nest = NEST.instantiate() as ModularNest
	root.add_child(nest)
	if OS.get_environment("ELFIENEST_FURNITURE_TEST_LAB") == "1": nest.set_meta("lab_action_preview", true)
	await process_frame
	await physics_frame
	await physics_frame
	if not require(nest.bake_navigation(), "Furniture checks need production navigation"): return
	if not require(await nest.wait_for_navigation_sync(), "Furniture navigation did not synchronize"): return
	var estate := nest.get_node("Generated/CompleteEstate")
	var desktop_proxies := 0
	for body: StaticBody3D in nest._estate_physics.find_children("*", "StaticBody3D", true, false):
		var shape := (body.get_child(0) as CollisionShape3D).shape
		if shape.has_meta("desktop_silhouette"):
			if not require(shape is ConcavePolygonShape3D, "Desktop must use one baked BVH, not runtime convex decomposition"): return
			desktop_proxies += 1
	if not require(desktop_proxies == 32, "All 32 bedroom worktops must load baked desktop silhouettes before playback"): return
	for body: StaticBody3D in nest._estate_physics.find_children("*", "StaticBody3D", true, false):
		var source := str(body.get_meta("source_node", ""))
		if source.is_empty(): continue
		var mesh := estate.find_child(source, true, false) as MeshInstance3D
		if mesh == null: continue
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if extras.get("kind") == "sofa" or str(mesh.name) in ["Soft V2 continuous sculpted back and integrated arms", "Soft V2 single rounded upholstered body"]:
			if not require((body.get_child(0) as CollisionShape3D).shape is ConcavePolygonShape3D, "Sofa recess filled by a convex collider: " + str(mesh.name)): return
	var other_room_colliders := 0
	for body: StaticBody3D in nest._estate_physics.find_children("*","StaticBody3D",true,false):
		if str(body.get_meta("estate_module","")) == "M03": other_room_colliders += 1
	var cases := [
		["chair","dorm-01/chair-01","seat"],
		["chair-d","dorm-01/chair-04","seat","saevi"],
		["chair-d-dog","dorm-01/chair-04","seat","tovren"],
		["chair-other","dorm-02/chair-02","seat","tovren"],
		["sofa","central-01/sofa","seat","tovren"],
		["tea","terrace-07/sofa","seat","saevi"],
		["bench","courtyard/lakeside-seat","seat","saevi"],
		["sleep-back","dorm-01/bed-01","sleep-back"],
		["sleep-left","dorm-01/bed-01","sleep-left"],
		["sleep-right","dorm-01/bed-01","sleep-right"],
	]

	var selected := OS.get_environment("ELFIENEST_FURNITURE_TEST_CASE")
	if selected.is_empty(): selected = default_cases()
	var species := OS.get_environment("ELFIENEST_FURNITURE_TEST_SPECIES")
	if species.is_empty(): species = "tovren"
	if not require(species in ["saevi", "tovren"], "Unknown test species"): return
	var covers: Dictionary = {}
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		if str(mesh.get_meta("extras",{}).get("piece","")) == "bed_cover": covers[mesh] = mesh.mesh
	for item: Array in cases:
		if not selected.is_empty() and item[0] not in selected.split(","): continue
		_audited = false
		_preparation_frames = 0
		var marker := nest.resolve_anchor(item[1])
		if not require(marker != null, "Recovered target missing: " + item[1]): return
		var item_species := str(item[3]) if item.size() > 3 else ("saevi" if str(item[0]).begins_with("sleep-") else species)
		var actor := (load("res://characters/%s/%s.tscn" % [item_species, item_species]) as PackedScene).instantiate() as ElfieActor
		root.add_child(actor)
		actor.configure("test-" + item[0], marker.global_position)
		await physics_frame
		print("FURNITURE_CASE_START ", item[0])
		_watch(actor)
		var result: Dictionary = await actor.call("play_furniture_cycle", marker, item[1], item[0], item[2], nest)
		print("FURNITURE_CASE_RESULT ", item[0], " ", JSON.stringify(result))
		if not require(result.has("status"),"Furniture cycle returned no terminal status"): return
		if not require(result.status == "completed", "Recovered cycle failed: " + item[0] + " " + str(result)): return
		if item[2] == "seat" and not require(_audited,"Seat never reached a checked seated pose"): return
		if str(item[0]).begins_with("chair"):
			assert(actor.get_meta("furniture_cycle_stage", "") == "leave_seat")
			var carrier := marker.get_meta("furniture_carrier") as Node3D
			var source := marker.get_meta("furniture_source") as MeshInstance3D
			var owner_data: Dictionary = source.get_meta("extras")
			var mesh_ids: Array[int] = []
			for mesh: MeshInstance3D in carrier.find_children("*","MeshInstance3D",true,false):
				var data: Dictionary = mesh.get_meta("extras",{})
				if data.get("module") == owner_data.get("module") and data.get("resident") == owner_data.get("resident") and data.get("assembly") == "chair":
					mesh_ids.append(mesh.get_instance_id())
			for body: AnimatableBody3D in carrier.bodies:
				if not require(int(body.get_meta("source_mesh_id",0)) in mesh_ids,"Carrier bound a different chair instance"): return
		if item[0] == "chair" and species == "tovren":
			if not require(_preparation_frames >= 30, "Seat collision preparation blocked the render loop"): return
			print("DIRECT_SEAT_RENDER_FRAMES during_preparation=", _preparation_frames)
		if item[2] == "seat" and OS.get_environment("ELFIENEST_FURNITURE_TEST_REPEAT") == "1":
			var prior: Shape3D = actor.get_meta("seated_pose_cache").incoming[8][0]
			_audited = false
			actor._furniture_motion._cycle_deadline = Time.get_ticks_msec()+90000
			var repeated: Dictionary = await actor.play_furniture_cycle(marker,item[1],item[0]+"-repeat",item[2],nest)
			print("FURNITURE_REPEAT_RESULT ",item[0]," ",JSON.stringify(repeated))
			if not require(repeated.status == "completed" and _audited,"Repeated seated playback failed"): return
			if not require(actor.get_meta("seated_pose_cache").incoming[8][0] == prior,"Repeated playback rebuilt identical collision poses"): return
		actor.queue_free()
		await process_frame
		for cloth: MeshInstance3D in covers:
			if not require(cloth.mesh == covers[cloth], "Furniture cycle left a deformed duvet behind"): return
	var remaining := 0
	for body: StaticBody3D in nest._estate_physics.find_children("*","StaticBody3D",true,false):
		if str(body.get_meta("estate_module","")) == "M03": remaining += 1
	if not require(other_room_colliders == remaining,"Seating operation changed an unrelated room collider"): return
	print("PASS furniture world cases: ", selected if not selected.is_empty() else "M01-A direct chair and three sleep variants")
	nest.queue_free()
	await process_frame
	quit(0)

var _audited := false

var _preparation_frames := 0
func _watch(actor: ElfieActor) -> void:
	while is_instance_valid(actor):
		await physics_frame
		if not is_instance_valid(actor): return
		var stage := str(actor.get_meta("furniture_cycle_stage",""))
		if stage == "prepare_seat": _preparation_frames += 1
		if stage == "seated_idle" and not _audited:
			var audit := preload("res://runtime/actor/furniture_seated_collision.gd")
			var hands := audit.hands_clearance(actor)
			var tail := audit.tail_clearance(actor)
			tail.erase("overlap_indices")
			print("DIRECT_SKIN_AUDIT ",hands," ",tail)
			if not require(hands.Left.intrusions == 0 and hands.Right.intrusions == 0 and tail.distal_intrusions == 0,"Seated hands/tail intersect body"): return
			_audited = true
