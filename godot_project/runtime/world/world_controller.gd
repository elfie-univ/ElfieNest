class_name NestWorldRuntimeController
extends Node

const SEMANTIC_SCENE_INDEX := preload("res://runtime/world/semantic_scene_index.gd")
const SPATIAL_QUERIES := preload("res://runtime/world/spatial_queries.gd")

signal runtime_event(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
)

var navigation_ready := false
var _nest: ModularNest
var _actor_provider: Callable
var _speech_commands: Dictionary = {}
var _visual_observation_commands: Dictionary = {}


func setup(nest: ModularNest, actor_provider: Callable = Callable()) -> void:
	_nest = nest
	_actor_provider = actor_provider


func set_actor_provider(actor_provider: Callable) -> void:
	_actor_provider = actor_provider


func resolve_speech_reach(command: Dictionary) -> void:
	var command_id := String(command.get("command_id", ""))
	var actor_id := String(command.get("actor_id", ""))
	var profile := String(command.get("acoustic_profile", "normal"))
	if command_id.is_empty() or actor_id.is_empty() or _speech_commands.has(command_id):
		return
	_speech_commands[command_id] = actor_id
	var range := SPATIAL_QUERIES.speech_range(profile)
	if range <= 0.0:
		return
	var speaker := _actor_by_id(actor_id)
	if speaker == null:
		return
	var speaker_zone := _nest.nearest_zone_id(speaker.global_position)
	var audience: Array[String] = []
	for other_actor: Node3D in _actor_instances():
		var other_id := String(other_actor.get("elfie_id"))
		if other_id.is_empty() or other_id == actor_id:
			continue
		if _nest.nearest_zone_id(other_actor.global_position) != speaker_zone:
			continue
		if speaker.global_position.distance_to(other_actor.global_position) > range:
			continue
		if not SPATIAL_QUERIES.has_line_of_sight(
			speaker.get_world_3d(),
			speaker.global_position + Vector3.UP * SPATIAL_QUERIES.VISUAL_EYE_HEIGHT,
			other_actor.global_position + Vector3.UP * SPATIAL_QUERIES.ACTOR_TARGET_HEIGHT,
			other_actor,
			[speaker.get_rid(), other_actor.get_rid()],
		):
			continue
		audience.append(other_id)
	audience.sort()
	runtime_event.emit(
		"speech_reach",
		{
			"command_id": command_id,
			"actor_id": actor_id,
			"zone_id": speaker_zone,
			"audience_actor_ids": audience,
		},
		command_id,
	)


func resolve_visual_observation(command: Dictionary) -> void:
	var observation_id := String(command.get("observation_id", ""))
	var actor_id := String(command.get("actor_id", ""))
	if (
		observation_id.is_empty()
		or actor_id.is_empty()
		or _visual_observation_commands.has(observation_id)
	):
		return
	_visual_observation_commands[observation_id] = actor_id
	var observer := _actor_by_id(actor_id)
	if observer == null:
		return
	var max_results := clampi(int(command.get("max_results", 32)), 1, 64)
	var observer_zone := _nest.nearest_zone_id(observer.global_position)
	var candidates: Array[String] = []
	for other_actor: Node3D in _actor_instances():
		var other_id := String(other_actor.get("elfie_id"))
		if (
			other_id.is_empty()
			or other_id == actor_id
			or _nest.nearest_zone_id(other_actor.global_position) != observer_zone
		):
			continue
		if _is_visible(
			observer,
			other_actor.global_position + Vector3.UP * SPATIAL_QUERIES.ACTOR_TARGET_HEIGHT,
			other_actor,
		):
			candidates.append("actor/%s" % other_id)
	for anchor_id in SEMANTIC_SCENE_INDEX.sorted_anchor_ids(_nest.semantic_anchor_ids()):
		var marker := _nest.resolve_anchor(anchor_id)
		if marker == null or _nest.nearest_zone_id(marker.global_position) != observer_zone:
			continue
		if _is_visible(observer, marker.global_position + Vector3.UP * 0.6):
			candidates.append("anchor/%s" % anchor_id)
	var manifest := _nest.scene_manifest()
	for semantic_facility_id in SEMANTIC_SCENE_INDEX.active_facility_ids(
		manifest,
		observer_zone,
	):
		var facility_id := semantic_facility_id.trim_prefix("facility/")
		var facility_marker := _nest.resolve_facility(facility_id)
		if facility_marker == null:
			continue
		if _is_visible(
			observer,
			facility_marker.global_position + Vector3.UP * 0.6,
			facility_marker,
		):
			candidates.append(semantic_facility_id)
	candidates.sort()
	if candidates.size() > max_results:
		candidates.resize(max_results)
	runtime_event.emit(
		"visual_observation",
		{
			"observation_id": observation_id,
			"actor_id": actor_id,
			"zone_id": observer_zone,
			"visible_semantic_ids": candidates,
		},
		observation_id,
	)


func _is_visible(observer: Node3D, target_position: Vector3, target: Node3D = null) -> bool:
	if not SPATIAL_QUERIES.within_visual_cone(observer, target_position):
		return false
	var eye := observer.global_position + Vector3.UP * SPATIAL_QUERIES.VISUAL_EYE_HEIGHT
	return SPATIAL_QUERIES.has_line_of_sight(
		observer.get_world_3d(),
		eye,
		target_position,
		target,
		[observer.get_rid()],
	)


func _actor_instances() -> Array[Node3D]:
	if not _actor_provider.is_valid():
		return []
	var raw: Variant = _actor_provider.call()
	if not raw is Array:
		return []
	var result: Array[Node3D] = []
	for value: Variant in raw as Array:
		if value is Node3D:
			result.append(value as Node3D)
	return result


func _actor_by_id(actor_id: String) -> Node3D:
	for actor: Node3D in _actor_instances():
		if String(actor.get("elfie_id")) == actor_id:
			return actor
	return null


func configure_world(
	config: Dictionary,
	cause_id: String,
) -> Dictionary:
	navigation_ready = false
	var result := _nest.apply_world_config(config)
	if not bool(result.get("accepted", false)):
		runtime_event.emit("config_rejected", result, cause_id)
		return result

	await get_tree().process_frame
	var manifest := result.get("manifest", {}) as Dictionary
	if not _prepare_semantic_anchors(manifest) or not _nest.bake_navigation():
		var failure := {
			"accepted": false,
			"code": "navigation_not_ready",
			"world_revision": _nest.world_revision,
		}
		runtime_event.emit("startup_error", failure, cause_id)
		return failure
	if not await _wait_for_navigation_sync():
		var sync_failure := {
			"accepted": false,
			"code": "navigation_sync_timeout",
			"world_revision": _nest.world_revision,
		}
		runtime_event.emit("startup_error", sync_failure, cause_id)
		return sync_failure

	navigation_ready = true
	runtime_event.emit("scene_manifest", manifest, cause_id)
	runtime_event.emit(
		"world_configured",
		{
			"configured": true,
			"navigation_ready": true,
		},
		cause_id,
	)
	return result


func _wait_for_navigation_sync() -> bool:
	var navigation_map := _nest.get_world_3d().navigation_map
	for _frame in range(30):
		await get_tree().physics_frame
		if (
			NavigationServer3D.map_get_iteration_id(navigation_map) > 0
			and not NavigationServer3D.map_get_regions(navigation_map).is_empty()
		):
			await get_tree().physics_frame
			await get_tree().physics_frame
			return true
	return false


func _prepare_semantic_anchors(manifest: Dictionary) -> bool:
	var raw_anchors: Variant = manifest.get("anchors", [])
	if not raw_anchors is Array:
		return false
	for raw_anchor: Variant in raw_anchors as Array:
		if not raw_anchor is Dictionary:
			return false
	for anchor_id in SEMANTIC_SCENE_INDEX.active_anchor_ids(manifest):
		if _nest.resolve_anchor(anchor_id) == null:
			return false
	return true
