extends Node

const LAYERS := preload("res://runtime/world/collision_layers.gd")
var _nest: ModularNest
var _characters: Node3D
var _registered: Array[String] = []
var _last_publish := ""
var _lighting := "lighting-live"
var _last_refresh := -1000
var _live_environment: Dictionary = {}
var _demonstrations: Node

func bind_actor_controller(controller: Node) -> void:
	_demonstrations = preload("res://runtime/actor/action_demonstrations.gd").new()
	add_child(_demonstrations)
	_demonstrations.setup(_nest,controller)
	controller.preview_demonstrations = _demonstrations


func setup(nest: ModularNest, characters: Node3D) -> void:
	_nest = nest
	_characters = characters
	_nest.set_observation_hud_visible(false)
	if not OS.has_feature("web"): return
	JavaScriptBridge.eval(
		"(() => { window.__nestLabQueue = [];"
		+ " window.addEventListener('message', event => {"
		+ " if (event.origin !== location.origin || event.source !== parent) return;"
		+ " const d = event.data; if (!d || d.channel !== 'elfienest-nest-lab') return;"
		+ " if (d.type === 'camera' || d.type === 'catalog') window.__nestLabQueue.push(d);"
		+ " }); })()"
	)


func process_frame() -> void:
	if not OS.has_feature("web"): return
	if _nest.get_node_or_null("Generated/CompleteEstate") == null: return
	_nest.add_lighting_observer_views()
	var now := Time.get_ticks_msec()
	if now - _last_refresh >= 300:
		_last_refresh = now
		_refresh_actors()
		_publish()
	var raw: Variant = JavaScriptBridge.eval("JSON.stringify(window.__nestLabQueue.splice(0))")
	if not raw is String: return
	var messages: Variant = JSON.parse_string(raw)
	if not messages is Array: return
	for message: Variant in messages:
		if not message is Dictionary: continue
		if message.get("type") == "camera": camera_command(message)
		_publish(true)


func camera_command(message: Dictionary) -> bool:
	if _nest.get_node_or_null("Generated/CompleteEstate") == null: return false
	_nest.add_lighting_observer_views()
	match str(message.get("action", "")):
		"select":
			var view := str(message.get("view_id", ""))
			if not _nest.select_observer_camera_by_id(view): return false
			if view.begins_with("lighting-"): _lighting = view
			if view == "lighting-live" and not _live_environment.is_empty():
				_nest.apply_observer_environment(_live_environment)
		"environment":
			var environment: Variant = message.get("environment")
			if not valid_live_environment(environment): return false
			_live_environment = environment.duplicate()
			if _lighting == "lighting-live": _nest.apply_observer_environment(_live_environment)
		"reset":
			_nest.reset_observer_camera()
		"scene":
			var target := str(message.get("target", ""))
			if target.begins_with("door-"):
				if _nest._estate_physics == null or not _nest._estate_physics.preview_door(target, str(message.get("mode", ""))): return false
				return _focus_scene(target)
			if target == "waterfall":
				return _focus_scene(target)
			var water := _nest.get_node_or_null("Generated/ObserverFountainLighting")
			if water == null or not message.get("paused") is bool: return false
			if not water.set_component_paused(target, bool(message["paused"])): return false
			return _focus_scene(target)
		"demonstration":
			if _demonstrations == null: return false
			_demonstrations.play(str(message.get("actor_id","")),str(message.get("demonstration_id","")))
		"pause":
			if not message.get("paused") is bool: return false
			_set_presentation_paused(bool(message["paused"]))
		_:
			return false
	return true


func _door_label(door: Dictionary) -> String:
	var source := str(door.label)
	for index in range(1, 9):
		var module_name := "M%02d" % index
		if source.contains(module_name): return module_name + " 卧室门"
	return "主楼入口·" + ("左门" if source.to_lower().contains("left") else "右门")


func _focus_scene(target: String) -> bool:
	var view_id := "scene-" + target
	if not _nest.observer_camera_catalog()["views"].any(func(view: Dictionary) -> bool: return view.id == view_id):
		var center: Vector3
		var position: Vector3
		var label := ""
		var field_of_view := 65.0
		if target.begins_with("door-"):
			var index := int(target.trim_prefix("door-"))
			var door: Dictionary = _nest._estate_physics._doors[index]
			center = door.center
			var normal := (door.offset as Vector3).cross(Vector3.UP).normalized()
			# Observe bedroom doors from the central hall, not from inside a wall.
			if normal.dot(center - _nest.global_position) > 0: normal = -normal
			# Close framing keeps low railings out of the lower half of the image,
			# even when the ray to the door centre clears the top of a railing.
			position = center + normal * 1.9 + Vector3.UP * 0.3
			field_of_view = 85.0
			var query := PhysicsRayQueryParameters3D.create(center, position, LAYERS.PERCEPTION_MASK)
			var excluded: Array[RID] = []
			for leaf: Dictionary in _nest._estate_physics._doors:
				excluded.append((leaf.body as CollisionObject3D).get_rid())
			query.exclude = excluded
			var hit := _nest.get_world_3d().direct_space_state.intersect_ray(query)
			if not hit.is_empty():
				position = (hit.position as Vector3) - (position - center).normalized() * 0.35
				field_of_view = clampf(rad_to_deg(2.0 * atan(1.7 / position.distance_to(center))), 65.0, 105.0)
			label = _door_label(_nest._estate_physics.preview_doors()[index])
		elif target == "waterfall":
			var estate := _nest.get_node("Generated/CompleteEstate")
			var curtain := estate.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
			if curtain == null: return false
			var bounds := curtain.global_transform * curtain.get_aabb()
			center = bounds.get_center()
			var outward := curtain.global_basis.x
			outward.y = 0.0
			if outward.is_zero_approx(): return false
			var width := maxf(bounds.size.z, 1.0)
			position = center + outward.normalized() * width * 1.4 + Vector3.UP * width * 1.2
			field_of_view = 50.0
			label = "瀑布"
		else:
			var estate := _nest.get_node("Generated/CompleteEstate")
			var source := "Reference fountain water" if target == "fountain" else "COMPLETE Inset natural lake"
			var mesh := estate.find_child(source, true, false) as MeshInstance3D
			if mesh == null: return false
			var bounds := mesh.global_transform * mesh.get_aabb()
			center = bounds.get_center()
			var radius := maxf(bounds.size.x, bounds.size.z) * 0.5
			var outward := center - _nest.global_position
			outward.y = 0
			position = center + outward.normalized() * (radius * 1.7 + 2.0) + Vector3.UP * (radius * 0.65 + 2.5)
			if target == "lake":
				# Stay on the west bank; framing the full long lake from beyond its
				# farthest edge puts the lens outside the authored backdrop.
				position = Vector3(bounds.position.x - 2.0, center.y + 3.5, center.z)
			center.y += 0.8 if target == "fountain" else 0.0
			label = "喷泉" if target == "fountain" else "湖面波浪／波光"
		_nest._add_complete_view(_nest.get_node("Generated"), view_id, label, position, center, field_of_view)
	return _nest.select_observer_camera_by_id(view_id)


func catalog() -> Dictionary:
	var result := _nest.observer_camera_catalog()
	result.merge({"channel": "elfienest-nest-lab", "kind": "catalog", "lighting": _lighting})
	var actors: Array[Dictionary] = []
	for child: Node in _characters.get_children():
		if not child is ElfieActor: continue
		var actor := child as ElfieActor
		var player := actor.get_node("AnimationPlayer") as AnimationPlayer
		var animations: Array[String] = []
		for name: String in ActorAnimationRuntime.SHARED_ANIMATIONS:
			if player.has_animation(name): animations.append(name)
		actors.append({"actor_id": actor.elfie_id, "animations": animations,
			"demonstrations": _demonstrations.catalog(actor.elfie_id) if _demonstrations != null else [],
			"demonstration_state": str(_demonstrations.states.get(actor.elfie_id,"")) if _demonstrations != null else "",
			"posture": str(actor.get_meta("furniture_cycle_stage", actor.runtime_posture())), "command_id": str(actor.get("furniture_cycle_command")) if actor.has_method("play_furniture_cycle") and not str(actor.get("furniture_cycle_command")).is_empty() else actor.active_command_id})
	result["actors"] = actors
	result["scene_actions"] = []
	if _nest._estate_physics != null:
		for door: Dictionary in _nest._estate_physics.preview_doors():
			result["scene_actions"].append({"id":door.id,"label":_door_label(door),"paused":false,"mode":door.mode})
	var water := _nest.get_node_or_null("Generated/ObserverFountainLighting")
	if water != null:
		result["scene_actions"].append({"id": "fountain", "label": "喷泉", "paused": water.component_paused("fountain")})
		var estate := _nest.get_node_or_null("Generated/CompleteEstate")
		if estate != null and estate.find_child("Continuous shallow waterfall from solid spillway crest", true, false) != null:
			result["scene_actions"].append({"id": "waterfall", "label": "瀑布", "paused": water.component_paused("fountain")})
		result["scene_actions"].append({"id": "lake", "label": "湖面波浪／波光", "paused": water.component_paused("lake")})
	return result


func _refresh_actors() -> void:
	var current: Array[String] = []
	for child: Node in _characters.get_children():
		if child is ElfieActor and not (child as ElfieActor).elfie_id.is_empty():
			var actor := child as ElfieActor
			current.append(actor.elfie_id)
			_nest.register_observer_actor_camera(actor.elfie_id, actor)
	for actor_id: String in _registered:
		if actor_id not in current: _nest.remove_observer_actor_camera(actor_id)
	_registered = current


static func valid_live_environment(value: Variant) -> bool:
	return value is Dictionary and value.get("phase") in ["day", "dawn", "dusk", "night"] and value.get("lights_on") is bool and value.get("quiet_mode") is bool


func _set_presentation_paused(value: bool) -> void:
	_nest.set_observer_presentation_paused(value)
	if not OS.has_feature("web"): return
	# Freeze the displayed frame while the Lab authority continues processing.
	JavaScriptBridge.eval(
		"(() => { const old = document.getElementById('nest-lab-frozen'); if (old) old.remove();"
		+ (" const canvas = document.getElementById('canvas'); const img = document.createElement('img');"
		+ " img.id = 'nest-lab-frozen'; img.src = canvas.toDataURL('image/png');"
		+ " img.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:99';"
		+ " document.body.appendChild(img);" if value else "") + " })()"
	)


func _publish(force: bool = false) -> void:
	var serialized := JSON.stringify(catalog())
	if not force and serialized == _last_publish: return
	_last_publish = serialized
	JavaScriptBridge.eval("window.parent.postMessage(%s, window.location.origin)" % JSON.stringify(serialized))
