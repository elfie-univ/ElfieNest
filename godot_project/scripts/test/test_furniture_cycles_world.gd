extends SceneTree
const NEST := preload("res://rooms/nest.tscn")
var nest: ModularNest

func _initialize() -> void: call_deferred("run")
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
	var estate := nest.get_node("Generated/CompleteEstate")
	for body: StaticBody3D in nest._estate_physics.find_children("*", "StaticBody3D", true, false):
		var source := str(body.get_meta("source_node", ""))
		if source.is_empty(): continue
		var mesh := estate.find_child(source, true, false) as MeshInstance3D
		if mesh == null: continue
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if extras.get("kind") == "sofa" or str(mesh.name) in ["Soft V2 continuous sculpted back and integrated arms", "Soft V2 single rounded upholstered body"]:
			if not require((body.get_child(0) as CollisionShape3D).shape is ConcavePolygonShape3D, "Sofa recess filled by a convex collider: " + str(mesh.name)): return
	var cases := [
		["chair", "dorm-01/chair-01", "seat"],
		["bench-lake", "courtyard/lakeside-seat", "seat"],
		["bench-picnic", "courtyard/picnic-seat", "seat"],
		["sofa-central", "central-01/sofa", "seat"],
		["sofa-left", "central-01/sofa-left", "seat"],
		["sofa-right", "central-01/sofa-right", "seat"],
		["sofa-cinema", "terrace-01/sofa", "seat"],
		["sofa-tea", "terrace-07/sofa", "seat"],
		["sleep-back", "dorm-01/bed-01", "sleep-back"],
		["sleep-left", "dorm-01/bed-01", "sleep-left"],
		["sleep-right", "dorm-01/bed-01", "sleep-right"],
	]
	var selected := OS.get_environment("ELFIENEST_FURNITURE_TEST_CASE")
	var species := OS.get_environment("ELFIENEST_FURNITURE_TEST_SPECIES")
	if species.is_empty(): species = "tovren"
	if not require(species in ["saevi", "tovren"], "Unknown test species"): return
	for item: Array in cases:
		if not selected.is_empty() and item[0] not in selected.split(","): continue
		var marker := nest.resolve_anchor(item[1])
		if not require(marker != null, "Recovered target missing: " + item[1]): return
		var actor := (load("res://characters/%s/%s.tscn" % [species, species]) as PackedScene).instantiate() as ElfieActor
		root.add_child(actor)
		actor.configure("test-" + item[0], marker.global_position)
		await physics_frame
		print("FURNITURE_CASE_START ", item[0])
		var result: Dictionary = await actor.call("play_furniture_cycle", marker, item[1], item[0], item[2], nest)
		print("FURNITURE_CASE_RESULT ", item[0], " ", JSON.stringify(result))
		if not require(result.status == "completed", "Recovered cycle failed: " + item[0] + " " + str(result)): return
		actor.queue_free()
		await process_frame
	print("PASS furniture world cases: ", selected if not selected.is_empty() else "chair, three sofas and three sleep variants")
	nest.queue_free()
	await process_frame
	quit(0)
