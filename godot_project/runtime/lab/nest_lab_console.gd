extends Node

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
				return _nest._estate_physics != null and _nest._estate_physics.preview_door(target, str(message.get("mode", "")))
			var water := _nest.get_node_or_null("Generated/ObserverFountainLighting")
			if water == null or not message.get("paused") is bool: return false
			return water.set_component_paused(target, bool(message["paused"]))
		"demonstration":
			if _demonstrations == null: return false
			_demonstrations.play(str(message.get("actor_id","")),str(message.get("demonstration_id","")))
		"pause":
			if not message.get("paused") is bool: return false
			_set_presentation_paused(bool(message["paused"]))
		_:
			return false
	return true


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
			result["scene_actions"].append({"id":door.id,"label":door.label,"paused":false,"mode":door.mode})
	var water := _nest.get_node_or_null("Generated/ObserverFountainLighting")
	if water != null:
		result["scene_actions"].append({"id": "fountain", "label": "喷泉", "paused": water.component_paused("fountain")})
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
