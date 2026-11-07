extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var nest := load("res://nest/nest.tscn").instantiate() as ModularNest
	nest.physical_authority = true
	root.add_child(nest)
	var characters := Node3D.new()
	root.add_child(characters)
	var world := NestWorldRuntimeController.new()
	root.add_child(world)
	world.setup(nest)
	var configured: Dictionary = await world.configure_world({"nest_id": "spawn-check", "bed_count": 32, "world_revision": 1}, "configure")
	if not configured.get("accepted", false):
		push_error("Authority world configuration failed")
		quit(1)
		return
	var controller := NestActorRuntimeController.new()
	root.add_child(controller)
	controller.setup(nest, characters, preload("res://runtime/species_catalog.gd").discover_actor_scenes(), true)
	var actors: Array[Dictionary] = []
	for species: String in ["saevi", "tovren", "myelle"]:
		actors.append({"actor_id": species + "-spawn", "species": species, "spawn_anchor_id": "dorm-01/bed-0%d" % (actors.size() + 1), "appearance": {}})
	var synced := controller.sync_actors(actors)
	if not synced.get("accepted", false):
		push_error("Authority failed to spawn all three species")
		quit(1)
		return
	for frame: Dictionary in controller.world_snapshot().actors:
		if frame.action_anchor_id == null or frame.posture != "idle" or frame.zone_id.is_empty():
			push_error("Spawn omitted its real semantic position")
			quit(1)
			return
	await process_frame
	print("PASS authority resident spawn: three species, physical world, real spawn anchors")
	quit()
