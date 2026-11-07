extends SceneTree

const CONSOLE := preload("res://runtime/lab/nest_lab_console.gd")
const NEST := preload("res://nest/nest.tscn")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var nest := NEST.instantiate() as ModularNest
	root.add_child(nest)
	var characters := Node3D.new()
	root.add_child(characters)
	var console := CONSOLE.new()
	root.add_child(console)
	console.setup(nest, characters)
	await process_frame
	if not check(console.camera_command({"action":"environment", "environment":{"phase":"dusk", "lights_on":true,"quiet_mode":false}}), "Cannot receive Nest environment"): return
	if not check(console.camera_command({"action": "select", "view_id": "central-1"}), "Cannot select actual estate camera"): return
	if not check(console.catalog()["active_id"] == "central-1", "Camera acknowledgement differs from selected view"): return
	if not check(not console.camera_command({"action": "select", "view_id": "missing"}), "Unknown camera was accepted"): return
	if not check(console.camera_command({"action": "select", "view_id": "lighting-night"}), "Missing Lab lighting preview"): return
	if not check(console.catalog()["active_id"] == "central-1", "Lighting changed the camera"): return
	if not check(not console.catalog()["scene_actions"].is_empty(), "Water presentation missing from scene actions"): return
	if not check(console.camera_command({"action": "scene", "target": "fountain", "paused": true}), "Cannot pause existing water presentation"): return
	if not check(console.catalog()["scene_actions"].filter(func(item: Dictionary) -> bool: return item.id == "fountain")[0]["paused"], "Water pause not acknowledged"): return
	if not check(not console.catalog()["presentation_paused"], "Water pause froze the entire view"): return
	var waterfall_items: Array = console.catalog()["scene_actions"].filter(func(item: Dictionary) -> bool: return item.id == "waterfall")
	if not check(waterfall_items.size() == 1 and waterfall_items[0].label == "瀑布", "The scene menu must offer one waterfall view"): return
	if not check(console.camera_command({"action":"scene", "target":"waterfall", "paused":false}), "Cannot select waterfall view"): return
	if not check(console.catalog()["active_id"] == "scene-waterfall", "Waterfall view did not select its camera"): return
	var water := nest.get_node("Generated/ObserverFountainLighting")
	if not check(water.component_paused("fountain"), "Selecting the waterfall view must not resume the fountain"): return
	var curtain := nest.get_node("Generated/CompleteEstate").find_child("Continuous shallow waterfall from solid spillway crest",true,false) as MeshInstance3D
	var fall := curtain.global_transform * curtain.get_aabb()
	var fall_camera := nest._active_camera()
	if not check(fall_camera.global_position.x > fall.end.x + 1.0 and fall_camera.global_position.y > fall.end.y, "Waterfall camera must face the outlet from above the lake"): return
	var edge_y := fall.get_center().y
	for point: Vector3 in [Vector3(fall.end.x,edge_y,fall.position.z-0.2),Vector3(fall.end.x,edge_y,fall.end.z+0.2),fall.position,fall.end]:
		var direction := (point-fall_camera.global_position).normalized()
		if not check(direction.dot(-fall_camera.global_basis.z) > cos(deg_to_rad(fall_camera.fov*0.48)), "Waterfall camera must frame the curtain and both sides"): return
	if not check(not console.camera_command({"action": "scene", "target": "missing", "paused": true}), "Unknown scene object accepted"): return
	console.camera_command({"action": "scene", "target": "fountain", "paused": false})
	for target in ["fountain", "lake"]:
		if not check(console.camera_command({"action":"scene", "target":target, "paused":false}), "Cannot preview " + target): return
		if not check(console.catalog()["active_id"] == "scene-" + target, "Water preview did not focus its own camera: " + target): return
		var camera := nest._active_camera()
		if not check(camera != null, "Water preview has no actual camera"): return
		if target == "lake":
			var mesh := nest.get_node("Generated/ObserverFountainLighting").lake as MeshInstance3D
			var center := (mesh.global_transform * mesh.get_aabb()).get_center()
			if not check(camera.global_position.distance_to(center) < 20.0, "Lake camera backed away beyond the shoreline/backdrop"): return
	var scene_items: Array = console.catalog()["scene_actions"]
	var labels: Array[String] = []
	for item: Dictionary in scene_items:
		if not item.id.begins_with("door-"): continue
		labels.append(str(item.label))
		if not check(str(item.label).contains("门") and not str(item.label).contains("Central") and not str(item.label).contains("movable"), "Model name leaked into door menu: " + str(item.label)): return
		for mode in ["open", "closed", "auto"]:
			if not check(console.camera_command({"action":"scene", "target":item.id, "mode":mode}), "Cannot preview door mode"): return
			if not check(console.catalog()["active_id"] == "scene-" + str(item.id), "Door preview kept unrelated camera"): return
			var door: Dictionary = nest._estate_physics._doors[int(str(item.id).trim_prefix("door-"))]
			if not check(nest._active_camera().global_position.distance_to(door.center) <= 2.0, "Door camera includes distant foreground furniture"): return
			var query := PhysicsRayQueryParameters3D.create(door.center, nest._active_camera().global_position, preload("res://runtime/world/collision_layers.gd").PERCEPTION_MASK)
			var excluded: Array[RID] = []
			for leaf: Dictionary in nest._estate_physics._doors: excluded.append((leaf.body as CollisionObject3D).get_rid())
			query.exclude = excluded
			if not check(nest.get_world_3d().direct_space_state.intersect_ray(query).is_empty(), "Furniture or railing obscures door camera: " + str(item.label)): return
	if not check(labels.size() == 10 and labels.all(func(label: String) -> bool: return labels.count(label) == 1), "Door labels are incomplete or ambiguous"): return
	var view_count: int = console.catalog()["views"].size()
	console.camera_command({"action":"scene", "target":"fountain", "paused":false})
	if not check(console.catalog()["views"].size() == view_count, "Repeated preview duplicated scene cameras"): return
	if not check(console.camera_command({"action": "pause", "paused": true}), "Cannot pause local presentation"): return
	if not check(not paused, "Observation pause stopped the authority simulation"): return
	if not check(console.catalog()["presentation_paused"], "Pause state not acknowledged"): return
	console.camera_command({"action": "pause", "paused": false})
	if not check(console.camera_command({"action": "reset"}), "Cannot restore view"): return
	nest.queue_free()
	characters.queue_free()
	console.queue_free()
	await process_frame
	print("PASS: Nest Lab uses production cameras and light preview without pausing authority")
	quit(0)


func check(condition: bool, message: String) -> bool:
	if not condition:
		push_error(message)
		quit(1)
	return condition
