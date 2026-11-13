extends SceneTree

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var nest := load("res://nest/nest.tscn").instantiate() as ModularNest
	nest.set_meta("lab_action_preview",true)
	root.add_child(nest)
	await process_frame
	var configured := nest.apply_world_config({"nest_id":"catalog-regression","bed_count":32,"world_revision":1})
	if not require(configured.get("accepted",false) and nest.bake_navigation(), "Action menus require matching spatial data"): return
	if not require(await nest.wait_for_navigation_sync(), "Action catalog navigation did not synchronize"): return
	# Production startup aligns semantic approaches after navigation sync.
	if not require(nest.validate_navigation_anchors(), "Action catalog anchors must be aligned and reachable"): return
	var characters := Node3D.new()
	root.add_child(characters)
	var controller := preload("res://runtime/actor/actor_controller.gd").new()
	root.add_child(controller)
	controller.setup(nest,characters,{"tovren":load("res://characters/tovren/tovren.tscn")},true)
	var result := controller.sync_actors([{"actor_id":"catalog-actor","species":"tovren","appearance":{},"spawn_anchor_id":"dorm-01/bed-01"}])
	if not require(result.get("accepted",false), "Actor must spawn through the normal controller"): return
	var console := preload("res://runtime/lab/nest_lab_console.gd").new()
	root.add_child(console)
	console.setup(nest,characters)
	console.bind_actor_controller(controller)
	var catalog: Dictionary = console.catalog()
	if not require(catalog.scene_actions.filter(func(item: Dictionary) -> bool: return str(item.id).begins_with("door-")).size() == 10, "Retain all ten door actions"): return
	if not require(catalog.actors.size() == 1, "Actor catalog disappeared"): return
	var actor: Dictionary = catalog.actors[0]
	if not require(actor.animations.size() == ActorAnimationRuntime.SHARED_ANIMATIONS.size()+2 and actor.animations.has("nod_head") and actor.animations.has("shake_head"), "Retain every shared actor animation"): return
	if not require(actor.demonstrations.size() == 7 and actor.demonstrations.all(func(item: Dictionary) -> bool: return item.available), "Retain all seven reachable demonstrations: " + JSON.stringify(actor.demonstrations)): return
	print("PASS: ten doors, ",actor.animations.size()," animations and seven reachable actor demonstrations")
	nest.queue_free()
	controller.queue_free()
	console.queue_free()
	characters.queue_free()
	await process_frame
	quit(0)
